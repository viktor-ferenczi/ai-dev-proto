import json
import os
import traceback
from typing import Set, Optional

from pydantic import BaseModel

from .model import Solution, Task
from .model import TaskState, Source, Generation, GenerationState, SourceState, Feedback
from .working_copy import WorkingCopy
from ..code_map.model import Graph, Symbol, Category
from ..code_map.parsers import detect_parser
from ..common.async_helpers import AsyncPool
from ..common.config import C
from ..common.util import render_workflow_template, regex_from_lines, extract_code_blocks, join_lines, replace_tripple_backquote, write_text_file, render_markdown_template, read_binary_file, decode_normalize
from ..editing.model import Patch
from ..engine.params import GenerationParams, Constraint

SYSTEM_CODING_ASSISTANT = '''\
You are a helpful coding assistant experienced in C#, .NET Core., HTML, JavaScript and Python.
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
                await self.find_source_files()
                if task.state == TaskState.FAILED:
                    return

                source_lines = await self.build_code_map()
                if task.state == TaskState.FAILED:
                    return

                self.dump_task()
                await self.plan_task(source_lines)
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

    async def build_code_map(self) -> dict[str, list[str]]:
        task = self.task
        wc = self.wc

        graph = Graph.new()
        source_lines: dict[str, list[str]] = {}

        assert isinstance(wc, WorkingCopy)
        for path in task.paths:
            full_path = os.path.join(wc.project_dir, path)
            parser_cls = detect_parser(full_path)
            if parser_cls is None:
                continue
            parser = parser_cls()
            content = read_binary_file(full_path)
            parser.parse(graph, path, content)
            source_lines[path] = decode_normalize(content).split('\n')

        task.code_map = graph
        return source_lines

    async def plan_task(self, source_lines: dict[str, list[str]]):
        task = self.task

        task.planning_generations = []

        class PlanResponse(BaseModel):
            state: str
            names: list[str]

        response_schema = PlanResponse.model_json_schema()

        symbols: Set[Symbol] = set()
        plan: Optional[str] = None

        for _ in range(C.MAX_PLANNING_STEPS):

            facts = [join_lines(source_lines[symbol.path][symbol.block.begin:symbol.block.end]) for symbol in symbols]

            instruction = render_workflow_template(
                'plan',
                task=task,
                facts=facts,
                response_schema=response_schema,
            )
            constraint = Constraint.from_regex(r'Step-by-step plan to implement the TASK:\n\n.*\n\n```\n\{"state": "(INCOMPLETE|READY)", "names": (\[\]|\[".*?"\]|\[".*?"(?:, ".*?")+\])\}\n```\n')
            params = GenerationParams(max_tokens=2000, temperature=self.temperature, constraint=constraint)
            gen = Generation.new(SYSTEM_CODING_ASSISTANT, instruction, params)
            task.planning_generations.append(gen)
            await gen.wait()

            if gen.state == GenerationState.FAILED:
                task.state = TaskState.FAILED
                task.error = f'Failed to plan the implementation:\n\n{gen.error}'
                return

            completion = gen.completions[0]
            parts = completion.rsplit('\n```\n', 2)

            if len(parts) != 3:
                task.state = TaskState.FAILED
                task.error = f'The plan does not end in a code block'
                return

            if parts[-1].strip():
                task.state = TaskState.FAILED
                task.error = f'Trailing garbage in plan completion'
                return

            response = PlanResponse(**json.loads(parts[1]))

            if response.state == 'READY':
                plan = parts[0].strip()
                break

            if response.state != 'INCOMPLETE':
                task.state = TaskState.FAILED
                task.error = f'Invalid plan response state: {response.state}'
                return

            symbol_names_and_paths = {symbol.name for symbol in symbols}
            symbol_names_and_paths.update(symbol.path for symbol in symbols)
            new_names = [name for name in response.names if name not in symbol_names_and_paths]

            if not new_names:
                task.state = TaskState.FAILED
                task.error = f'Incomplete plan with no new names requested'
                return

            for name in new_names:
                for symbol in task.code_map.symbols.values():
                    if symbol.block is None:
                        continue
                    if symbol.category == Category.SOURCE:
                        if symbol.path == name:
                            symbols.add(symbol)
                    elif symbol.name == name:
                        symbols.add(symbol)

        if plan is None:
            task.state = TaskState.FAILED
            task.error = f'Failed to plan the implementation in {C.MAX_PLANNING_STEPS} steps'
            return

        task.plan = plan

        selected_paths = {symbol.path for symbol in symbols}

        for path in task.paths:
            if path in task.description:
                selected_paths.add(path)

        if not selected_paths:
            task.state = TaskState.FAILED
            task.error = f'Found no relevant source files'
            return

        task.sources = [
            Source.from_file(self.solution.folder, path)
            for path in sorted(selected_paths)
        ]

        task.state = TaskState.CODING

    async def find_relevant_sources_in_chunk(self, chunk: list[str], n: int) -> Generation:
        task = self.task

        instruction = render_workflow_template(
            'find_relevant_sources',
            task=task,
            paths=join_lines(['```'] + chunk + ['```']),
        )
        constraint = Constraint.from_regex(rf'```\n{regex_from_lines(chunk)}```\n')
        params = GenerationParams(n=n, max_tokens=4000, temperature=self.temperature, constraint=constraint)
        gen = Generation.new(SYSTEM_CODING_ASSISTANT, instruction, params)
        task.source_selection_generations.append(gen)
        await gen.wait()
        return gen

    async def code_task(self):
        task = self.task

        if not task.sources:
            task.state = TaskState.FAILED
            task.error = f'No source files to change'
            return

        async with AsyncPool() as pool:
            for source in task.sources:
                pool.run(self.process_source(source))

            while pool:
                await pool.wait()
                self.dump_task()

        failed_sources = []
        for source in task.sources:
            if source.state == SourceState.FAILED:
                failed_sources.append(source)
        if failed_sources:
            task.state = TaskState.FAILED
            task.error = join_lines(
                ['Failed to change source file(s):'] +
                [source.document.path for source in failed_sources]
            )
            return

        self.dump_task()

        assert all(source.state in (SourceState.COMPLETED, SourceState.SKIP) for source in task.sources), 'Invalid source states'

        if not any(source.state == SourceState.COMPLETED for source in task.sources):
            task.state = TaskState.FAILED
            task.error = f'No changes made to any of the source files'
            return

        task.state = TaskState.TESTING

    async def process_source(self, source: Source):
        task = self.task

        if source.relevant is None:
            await self.find_relevant_code(source)
            if source.state != SourceState.PENDING or not task.is_wip:
                return

        if source.implementation is None:
            await self.implement_task_in_source(source)
            if source.state != SourceState.PENDING or not task.is_wip:
                return

        source.state = SourceState.COMPLETED

    async def find_relevant_code(self, source: Source):
        task = self.task

        instruction = render_workflow_template(
            'find_relevant_code',
            task=task,
            source=source.document.code_block,
        )

        code_block_type = source.document.doctype.code_block_type
        constraint = Constraint.from_regex(f'```{code_block_type}\n{regex_from_lines(source.document.lines)}```\n')
        params = GenerationParams(max_tokens=4000, temperature=self.temperature, constraint=constraint)
        gen = Generation.new(SYSTEM_CODING_ASSISTANT, instruction, params)

        source.relevant_generation = gen
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            source.state = SourceState.FAILED
            source.error = f'Failed to find relevant code lines'
            return

        for completion in gen.completions:
            try:
                patch = Patch.from_completion(source.document, completion)
            except ValueError:
                continue
            if patch.hunks:
                break
        else:
            # Found no relevant code lines
            source.state = SourceState.SKIP
            return

        patch.merge_hunks()
        source.relevant = patch.hunks[0]

    async def implement_task_in_source(self, source: Source):
        task = self.task

        instruction = render_workflow_template(
            'implement_task',
            task=task,
            source=source.relevant.code_block,
        )

        code_block_type = source.document.doctype.code_block_type
        constraint = Constraint.from_regex(f'```{code_block_type}\n(.*?\n)*```\n')
        params = GenerationParams(max_tokens=4000, temperature=self.temperature, constraint=constraint)
        gen = Generation.new(SYSTEM_CODING_ASSISTANT, instruction, params)

        source.patch_generation = gen
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            source.state = SourceState.FAILED
            source.error = f'Failed to implement the task'
            return

        for completion in gen.completions:
            code_blocks = extract_code_blocks(completion)
            if code_blocks:
                replacement_lines = code_blocks[-1].split('\n')
                break
        else:
            source.state = SourceState.FAILED
            source.error = 'Empty implementation'
            return

        source.relevant.replacement = replacement_lines
        source.patch = Patch.from_hunks(source.relevant.document, [source.relevant])
        source.implementation = source.patch.apply()

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
