import json
import os
import re
import traceback
from typing import Set

from pydantic import BaseModel

from .model import Solution, Task
from .model import TaskState, Source, Generation, GenerationState, SourceState, Feedback
from .working_copy import WorkingCopy
from ..code_map.model import Graph, Category, Symbol
from ..code_map.parsers import detect_parser
from ..common.util import render_workflow_template, extract_code_blocks, replace_tripple_backquote, write_text_file, render_markdown_template, read_binary_file
from ..editing.model import Patch, Block, Hunk
from ..engine.params import GenerationParams, Constraint

SYSTEM_CODING_ASSISTANT = '''\
You are a helpful coding assistant experienced in C#, .NET Core, HTML, JavaScript and Python.
'''


class TaskProcessor:

    def __init__(self, solution: Solution, task: Task, working_copy: WorkingCopy):
        self.solution: Solution = solution
        self.task: Task = task
        self.wc: WorkingCopy = working_copy

        # FIXME: Make this varying
        self.temperature: float = 0.2

    async def run(self):
        async with self.wc:
            self.wc.ensure_branch(self.task.branch)
            await self.drive_through_states()

    async def drive_through_states(self):
        task = self.task

        try:
            self.dump_task()

            if task.state == TaskState.PLANNING:

                # FIXME: Produce only once for each git hash
                await self.find_source_files()
                if task.state == TaskState.FAILED:
                    return

                # FIXME: Produce only once for each git hash
                await self.build_code_map()
                if task.state == TaskState.FAILED:
                    return

                await self.find_relevant_sources()
                if task.state == TaskState.FAILED:
                    return

                self.dump_task()

            if task.state == TaskState.CODING:
                await self.code_task()
                self.dump_task()

            if task.state == TaskState.TESTING:
                await self.build_and_test_task()
                self.dump_task()

            if task.state == TaskState.REVIEW:
                print(f'Task completed: {task.id}')

        except Exception:
            tb = traceback.format_exc()
            task.state = TaskState.FAILED
            task.error = f'Unexpected error:\n{tb}'
            print('---')
            print(tb)
            print('---')

        if task.state == TaskState.FAILED:
            print(f'Task failed: {task.id}')

        self.dump_task()

    def dump_task(self) -> None:
        task = self.task

        json_path = os.path.join(self.wc.tasks_dir, f'{task.id}.json')
        write_text_file(json_path, task.model_dump_json(indent=2))

        task_md = render_markdown_template('task', task=task)
        audit_path = os.path.join(self.wc.audit_dir, f'{task.id}.md')
        write_text_file(audit_path, task_md)

        if task.state == TaskState.REVIEW:
            write_text_file(self.wc.latest_path, task_md)

    async def find_source_files(self):
        task = self.task
        wc = self.wc

        assert isinstance(wc, WorkingCopy)
        ignored_paths = wc.list_ignored_paths()
        if ignored_paths is None:
            # FIXME: Code to work with a test case
            if self.solution.name == 'Test':
                ignored_paths = set()
            else:
                task.state = TaskState.FAILED
                task.error = 'Could not list files ignored from the repository'
                return

        paths = [
            path for path in self.solution.iter_relative_source_paths()
            if path not in ignored_paths
               and '/.' not in f'/{path}/'  # FIXME: Too generic
               and '/Migrations/' not in f'/{path}/'  # FIXME: Solution specific
               and detect_parser(os.path.join(wc.project_dir, path)) is not None
        ]

        if not paths:
            task.state = TaskState.FAILED
            task.error = 'No source files in solution'
            return

        task.paths = paths

    async def build_code_map(self):
        task = self.task
        wc = self.wc

        graph = Graph.new()

        assert isinstance(wc, WorkingCopy)
        for path in task.paths:
            full_path = os.path.join(wc.project_dir, path)
            parser_cls = detect_parser(full_path)
            if parser_cls is None:
                continue
            parser = parser_cls()
            content = read_binary_file(full_path)
            parser.parse(graph, path, content)

        task.code_map = graph

    async def find_relevant_sources(self):
        task = self.task

        class Response(BaseModel):
            symbols: list[str]

        schema = Response.model_json_schema()

        instruction = render_workflow_template(
            'find_relevant_symbols',
            task=task,
            schema=schema,
        )
        constraint = Constraint.from_json_schema(schema)
        params = GenerationParams(max_tokens=1000, temperature=self.temperature, constraint=constraint)
        gen = Generation.new(SYSTEM_CODING_ASSISTANT, instruction, params)
        task.relevant_symbols_generation = gen
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            task.state = TaskState.FAILED
            task.error = f'Failed to find the relevant symbols:\n\n{gen.error}'
            return

        completion = gen.completions[0]

        names: Set[str] = set()
        names.update(json.loads(completion)['symbols'])

        # Symbols extracted by the model
        allowed_categories = {Category.NAMESPACE, Category.INTERFACE, Category.CLASS, Category.STRUCT, Category.RECORD, Category.VARIABLE}
        symbols = {symbol for symbol in task.code_map.symbols.values() if symbol.name in names and symbol.category in allowed_categories}
        print(f'Symbols mentioned in the task description: {sorted(s.id for s in symbols)!r}')

        # Relative paths mentioned by the task
        paths: Set[str] = {
            path
            for path in task.paths
            if path in task.description
        }
        print(f'Source paths mentioned in the task description: {sorted(paths)!r}')

        symbols_from_files: Set[Symbol] = set()
        symbols_from_files.update(
            symbol
            for symbol in task.code_map.symbols.values()
            if symbol.category == Category.SOURCE and symbol.path in paths
        )
        print(f'Symbols from source paths mentioned in the task description: {sorted(s.id for s in symbols_from_files)!r}')
        symbols.update(symbols_from_files)

        if not names and not paths:
            task.state = TaskState.FAILED
            task.error = f'Could not narrow down the symbols to work on based on the task description'
            return

        # Find all dependencies
        for symbol in list(symbols):
            dependencies: Set[Symbol] = {task.code_map.symbols[id] for id in task.code_map.relations[symbol.id]}
            print(f'Dependencies of {symbol.id}: {sorted(s.id for s in dependencies)!r}')
            symbols.update(s for r, s in task.code_map.iter_related(symbol) if s.category in allowed_categories)

        task.relevant_symbols = sorted(symbol.id for symbol in symbols)

        unique_paths = {symbol.path for symbol in symbols}
        task.sources = [
            Source.from_file(self.wc.project_dir, path)
            for path in unique_paths
        ]

        for source in task.sources:
            symbols_in_source = {symbol for symbol in symbols if symbol.path == source.document.path}
            blocks: list[Block] = sorted((symbol.block for symbol in symbols_in_source), key=lambda b: b.begin)
            hunks: list[Hunk] = []
            for block in blocks:
                if not hunks or not block.is_overlapping(hunks[-1].block):
                    hunk = Hunk.from_document(source.document, block)
                    hunks.append(hunk)
            patch = Patch.from_hunks(source.document, hunks)
            patch.merge_hunks()
            source.relevant = patch.hunks[0]

        task.state = TaskState.CODING

    async def code_task(self):
        task = self.task

        if not task.sources:
            task.state = TaskState.FAILED
            task.error = f'No source files to change'
            return

        instruction = render_workflow_template(
            'implement_task',
            task=task,
        )

        pattern = ''.join(
            fr'Path: `{re.escape(source.document.path)}`\n\n+```{source.document.code_block_type}\n(\n|[^`].*?\n)*```\n\n+'
            for source in task.sources
        )
        constraint = Constraint.from_regex(rf'<MODIFIED-SOURCE-CODE>\n\n+{pattern}</MODIFIED-SOURCE-CODE>\n')
        params = GenerationParams(max_tokens=4000, temperature=self.temperature, constraint=constraint)
        gen = Generation.new(SYSTEM_CODING_ASSISTANT, instruction, params)

        task.patch_generation = gen
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            task.state = TaskState.FAILED
            task.error = f'Failed to implement the task'
            return

        completion = gen.completions[0]

        i = completion.find('<MODIFIED-SOURCE-CODE>')
        j = completion.rfind('</MODIFIED-SOURCE-CODE>')
        assert 0 <= i < j, f'Missing or wrong modified source block: i={i}, j={j}'
        completion = completion[i + len('<MODIFIED-SOURCE-CODE>'):j].strip()
        completion = completion.replace('<MODIFIED-SOURCE-CODE>', '')
        completion = completion.replace('</MODIFIED-SOURCE-CODE>', '')

        for source in task.sources:
            path = source.document.path
            assert f'Path: `{path}`' in completion, f'Missing path: {path}'

        for source, code_block in zip(task.sources, extract_code_blocks(completion)):
            replacement_lines = code_block.split('\n')
            assert replacement_lines[0] == '//START'
            assert replacement_lines[-1] == '//FINISH'
            replacement_lines = replacement_lines[1:-1]
            source.relevant.replacement = replacement_lines
            source.patch = Patch.from_hunks(source.relevant.document, [source.relevant])
            source.implementation = source.patch.apply()
            source.state = SourceState.COMPLETED

        for source in task.sources:
            if source.state == SourceState.PENDING:
                source.state = SourceState.SKIP

        assert all(source.state in (SourceState.COMPLETED, SourceState.SKIP) for source in task.sources), 'Invalid source states'

        if not any(source.state == SourceState.COMPLETED for source in task.sources):
            task.state = TaskState.FAILED
            task.error = f'No changes made to any of the source files'
            return

        task.state = TaskState.TESTING

    async def build_and_test_task(self):
        task = self.task
        wc = self.wc

        assert isinstance(wc, WorkingCopy)

        for source in task.sources:
            if source.state == SourceState.COMPLETED:
                source.implementation.write(wc.project_dir)

        wc.format_code()

        for source in task.sources:
            if source.state == SourceState.COMPLETED:
                source.implementation.update(wc.project_dir)

        if not any(source.document.lines != source.implementation.lines for source in task.sources):
            task.state = TaskState.FAILED
            task.error = f'No changes made as part of the implementation'
            return

        error = wc.build()
        if error:
            await self.provide_feedback(task, 'build', error)
            task.state = TaskState.FAILED
            task.error = f'Failed to build solutions:\n\n{error}'
            return

        error = wc.test()
        if error:
            await self.provide_feedback(task, 'test', error)
            task.state = TaskState.FAILED
            task.error = f'Failed to test solutions:\n\n{error}'
            return

        for source in task.sources:
            if source.state == SourceState.COMPLETED:
                wc.stage_change(source.implementation.path)

        task.state = TaskState.REVIEW
        self.dump_task()

        wc.stage_change(wc.latest_path)
        wc.commit(task.id)

    async def provide_feedback(self, task: Task, critic: str, error: str):
        template_name = f'feedback_{critic}_error'
        instruction = render_workflow_template(
            template_name,
            task=task,
            error=replace_tripple_backquote(error),
        )

        params = GenerationParams(max_tokens=300, temperature=self.temperature)
        gen = Generation.new(SYSTEM_CODING_ASSISTANT, instruction, params)

        task.feedback_generation = gen
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            task.state = TaskState.FAILED
            task.error = f'Failed to generate feedback:\n\n{gen.error}'
            return

        gen.completions.sort(key=len)
        for completion in gen.completions:
            if completion.strip():
                break
        else:
            task.state = TaskState.FAILED
            task.error = f'Failed to generate feedback, all completions are empty.'
            return

        task.feedback = Feedback(
            critic=critic,
            criticism=completion,
        )

        # Do NOT append the feedback to task.feedbacks here,
        # that will happen on cloning the task for a retry
