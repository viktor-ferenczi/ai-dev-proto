import json
import os
import traceback
from typing import Set, List

from pydantic import BaseModel

from .model import Solution, Task, GenerationState, Generation
from .model import TaskState
from ..common.async_helpers import AsyncPool
from ..common.config import C
from .working_copy import WorkingCopy
from ..code_map.model import Graph, Category, Symbol
from ..code_map.parsers import detect_parser
from ..common.util import render_workflow_template, extract_code_blocks, replace_tripple_backquote, write_text_file, render_markdown_template, read_binary_file, iter_code_blocks, join_lines
from ..editing.model import Patch, Block, Hunk, Document
from ..engine.params import GenerationParams, Constraint


class ComparePlansResponse(BaseModel):
    reasoning: str
    better_implementation_plan: str


COMPARE_PLANS_RESPONSE_SCHEMA = ComparePlansResponse.model_json_schema()


class TaskProcessor:

    def __init__(self, solution: Solution, task: Task, working_copy: WorkingCopy):
        self.solution: Solution = solution
        self.task: Task = task
        self.wc: WorkingCopy = working_copy

        self.state_processors = {
            TaskState.PARSING: self.do_parsing,
            TaskState.PLANNING: self.do_planning,
            TaskState.CODING: self.do_coding,
            TaskState.TESTING: self.do_testing,
        }

    async def run(self):
        async with self.wc:
            self.wc.ensure_branch(self.task.branch)
            self.wc.roll_back_changes('.')
            await self.drive_through_states()

    async def drive_through_states(self):
        task = self.task

        try:
            self.dump_task()

            while task.is_wip:
                previous_state = task.state
                processor = self.state_processors[task.state]
                await processor()
                self.dump_task()
                assert task.state != previous_state, f'Task state has not progressed from {previous_state}'

        except Exception:
            tb = traceback.format_exc()
            task.state = TaskState.FAILED
            task.error = f'Unexpected error:\n{tb}'
            print('---')
            print(tb)
            print('---')

        if task.state == TaskState.REVIEW:
            print(f'Task completed: {task.id}')
        elif task.state == TaskState.FAILED:
            print(f'Task failed: {task.id}')
        else:
            print(f'Task {task.id} has invalid state: {task.state}')

    def dump_task(self) -> None:
        task = self.task

        json_path = os.path.join(self.wc.tasks_dir, f'{task.id}.json')
        write_text_file(json_path, task.model_dump_json(indent=2))

        task_md = render_markdown_template('task', task=task)
        audit_path = os.path.join(self.wc.audit_dir, f'{task.id}.md')
        write_text_file(audit_path, task_md)

        if task.state == TaskState.REVIEW:
            write_text_file(self.wc.latest_path, task_md)

    async def do_parsing(self):
        task = self.task
        task.generations = []

        commit_hash = self.wc.get_commit_hash()
        if not commit_hash:
            task.state = TaskState.FAILED
            task.error = 'Could not get the Git commit hash'
            return

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

        task.state = TaskState.PLANNING

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

        graph.cross_reference()

        task.code_map = graph

    async def find_relevant_sources(self):
        wc = self.wc
        task = self.task
        code_map = task.code_map

        class Response(BaseModel):
            symbols: List[str]

        schema = Response.model_json_schema()

        instruction = render_workflow_template(
            'find_relevant_symbols',
            task=task,
            schema=schema,
        )
        constraint = Constraint.from_json_schema(schema)
        params = GenerationParams(max_tokens=1000, temperature=0.2, constraint=constraint)
        gen = Generation.new('find_relevant_symbols', C.SYSTEM_CODING_ASSISTANT, instruction, params)

        task.generations.append(gen)
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            task.state = TaskState.FAILED
            task.error = f'Failed to find the relevant symbols:\n\n{gen.error}'
            return

        completion = gen.completions[0]

        names: Set[str] = set(json.loads(completion)['symbols'])
        relevant_symbols = {symbol for symbol in code_map.symbols.values() if symbol.name in names}

        related_symbols: Set[Symbol] = set()
        for symbol in relevant_symbols:
            related_symbols.update(code_map.iter(symbol.dependencies))
            related_symbols.update(code_map.iter(symbol.dependents))

        relevant_symbols.update(related_symbols)

        if not related_symbols:
            task.state = TaskState.FAILED
            task.error = f'Could not narrow down the relevant part of the code to work on based on the task description'
            return

        relevant_symbol_ids = {symbol.id for symbol in relevant_symbols}
        relevant_source_set = {code_map.find_parent(symbol, Category.SOURCE) for symbol in relevant_symbols}
        relevant_sources: List[Symbol] = sorted(relevant_source_set, key=lambda source: source.name)

        relevant_hunks: List[Hunk] = []
        for source in relevant_sources:

            relevant_blocks: List[Block] = []
            for symbol, depth in code_map.walk_children(source):
                if symbol.id in relevant_symbol_ids:
                    relevant_blocks.append(symbol.block)

            assert relevant_blocks, f'No relevant blocks found in source: {source.name}'

            relevant_blocks.sort(key=lambda b: b.begin)

            merged_blocks = [relevant_blocks[0]]
            for b in relevant_blocks[1:]:
                last = merged_blocks[-1]
                if b.end <= last.end:
                    continue
                if b.begin < last.end:
                    merged_blocks.append(Block.from_range(last.end, b.end))
                    continue
                merged_blocks.append(Block.from_range(b.begin, b.end))

            document = Document.from_file(wc.project_dir, source.name)
            hunks = [Hunk.from_document(document, b) for b in merged_blocks]
            patch = Patch.from_hunks(document, hunks)
            patch.merge_hunks()
            hunk = patch.hunks[0]
            relevant_hunks.append(hunk)

        task.relevant_symbols = relevant_symbol_ids
        task.relevant_paths = [source.name for source in relevant_sources]
        task.relevant_hunks = relevant_hunks

    async def do_planning(self):
        task = self.task
        task.generations = []

        instruction = render_workflow_template(
            'plan',
            task=task,
        )
        params = GenerationParams(n=8, beam_search=True, max_tokens=1000, temperature=0.7)
        plan_gen = Generation.new('plan', C.SYSTEM_CODING_ASSISTANT, instruction, params)
        task.generations.append(plan_gen)
        await plan_gen.wait()
        if plan_gen.state != GenerationState.COMPLETED:
            task.state = TaskState.FAILED
            task.error = 'Planning generation failed'
            return

        better_indices = []
        completion_indices = list(range(params.n))
        while len(completion_indices) > 1:
            for i, j in zip(completion_indices[::2], completion_indices[1::2]):
                instruction = render_workflow_template(
                    'compare_plans',
                    task=task,
                    schema=COMPARE_PLANS_RESPONSE_SCHEMA,
                    implementation_plan_alpha=plan_gen.completions[i],
                    implementation_plan_beta=plan_gen.completions[j],
                )
                constraint = Constraint.from_json_schema(COMPARE_PLANS_RESPONSE_SCHEMA)
                params = GenerationParams(n=11, max_tokens=1000, temperature=0.5, constraint=constraint)
                compare_gen = Generation.new('compare_plans', C.SYSTEM_CODING_ASSISTANT, instruction, params)
                task.generations.append(compare_gen)
                await compare_gen.wait()
                if compare_gen.state != GenerationState.COMPLETED:
                    task.state = TaskState.FAILED
                    task.error = f'Plan comparison generation failed: {compare_gen.error}'
                    return

                vote = sum(json.loads(response)['better_implementation_plan'] == 'ALPHA' for response in compare_gen.completions)
                better_indices.append(i if vote >= params.n // 2 else j)

            completion_indices = better_indices
            better_indices = []

        assert len(completion_indices) == 1
        task.plan = plan_gen.completions[completion_indices[0]]
        task.state = TaskState.CODING

    async def do_coding(self):
        task = self.task

        if not task.relevant_paths or not task.relevant_hunks:
            task.state = TaskState.FAILED
            task.error = f'No source files to change'
            return

        instruction = render_workflow_template(
            'implement_task',
            task=task,
        )

        pattern = rf'(Path: `(.*?)`\n\n`{{3}}([a-z]+)\n(\n|[^`].*?\n)*`{{3}}\n+)+'
        constraint = Constraint.from_regex(pattern)
        params = GenerationParams(n=8, beam_search=True, temperature=0.2, constraint=constraint)
        gen = Generation.new('implement_task', C.SYSTEM_CODING_ASSISTANT, instruction, params)

        task.generations.append(gen)
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            task.state = TaskState.FAILED
            task.error = f'Failed to implement the task'
            return

        for i, completion in enumerate(gen.completions):
            print(f'Trying to apply change from completion {i}')
            error = await self.apply_code_changes(completion)
            if not task.is_wip:
                return
            if not error:
                break
            self.wc.roll_back_changes('.')

        task.state = TaskState.TESTING

    async def apply_code_changes(self, completion: str) -> str:
        task = self.task

        completion_lines = completion.split('\n')

        try:
            code_blocks = iter_code_blocks(completion_lines)
        except ValueError as e:
            return f'Invalid code block(s) in completion: {e}'

        paths_seen: Set[str] = set()
        paths_to_stage: List[str] = []

        async with AsyncPool() as pool:
            for i, j in code_blocks:
                print(f'Completion code block {i}:{j}')

                path = ''
                for k in range(i - 1, -1, -1):
                    line = completion_lines[k].strip()
                    if not line:
                        continue
                    if line.startswith('Path: `') and line.endswith('`'):
                        path = line.split(': `', 1)[1][:-1]
                    break

                if not path:
                    return f'Cannot find path line before completion code block (ignored): {i}:{j}'

                if path in paths_seen:
                    print(f'Ignoring repeated path: {path}')
                    continue

                paths_seen.add(path)

                full_path = os.path.join(self.wc.project_dir, path)
                dir_path = os.path.dirname(full_path)
                exists = os.path.exists(full_path)

                code_lines = completion_lines[i + 1:j]
                code = join_lines(code_lines)

                os.makedirs(dir_path, exist_ok=True)

                if code.strip():
                    if exists:
                        print(f'Modify: {path}')
                        document = Document.from_file(self.wc.project_dir, path)
                        if len(pool) >= 16:
                            await pool.wait()
                        pool.run(self.reintegrate_code_change(document, code))
                    else:
                        print(f'Create: {path}')
                        write_text_file(full_path, code)
                    paths_to_stage.append(path)
                elif exists:
                    print(f'Delete: {path}')
                    os.remove(full_path)
                    paths_to_stage.append(path)

                if not task.is_wip:
                    return task.error

        for path in paths_to_stage:
            self.wc.stage_change(path)

        return ''

    async def reintegrate_code_change(self, document: Document, modifications: str):
        task = self.task

        if not modifications.strip():
            return

        modified_code_block = f'```{document.code_block_type}\n{replace_tripple_backquote(modifications)}\n```'
        instruction = render_workflow_template(
            'reintegrate_change',
            task=task,
            source_path=document.path,
            original_code_block=document.code_block,
            modified_code_block=modified_code_block,
            code_block_type=document.code_block_type,
        )

        constraint = Constraint.from_regex(rf'```{document.code_block_type}\n(\n|[^`].*?\n)+```\n\n')
        params = GenerationParams(n=4, temperature=0.2, constraint=constraint)
        gen = Generation.new('reintegrate_change', C.SYSTEM_CODING_ASSISTANT, instruction, params)
        task.generations.append(gen)
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            task.state = TaskState.FAILED
            task.error = f'Failed to reintegrate change to file: {document.path}'
            return

        for modified_code in extract_code_blocks(gen.completions[0]):
            break
        else:
            task.state = TaskState.FAILED
            task.error = f'No code blocks produced by the reintegrate change generation for file: {document.path}'
            return

        write_text_file(os.path.join(self.wc.project_dir, document.path), modified_code)

    async def do_testing(self):
        task = self.task
        wc = self.wc

        assert isinstance(wc, WorkingCopy)

        wc.format_code()

        if not wc.has_changes():
            task.state = TaskState.FAILED
            task.error = f'No changes made during the implementation'
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

        params = GenerationParams(max_tokens=500, temperature=0.2)
        gen = Generation.new(template_name, C.SYSTEM_CODING_ASSISTANT, instruction, params)

        task.generations.append(gen)
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

        # task.feedback = Feedback(
        #     critic=critic,
        #     criticism=completion,
        # )

        # Do NOT append the feedback to task.feedbacks here,
        # that will happen on cloning the task for a retry
