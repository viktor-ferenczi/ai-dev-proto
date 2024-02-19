import json
import os
import traceback
from typing import Set, List

from pydantic import BaseModel

from .model import Solution, Task, GenerationState, Generation
from .model import TaskState, Source, Feedback
from ..common.async_helpers import AsyncPool
from ..common.config import C
from .working_copy import WorkingCopy
from ..code_map.model import Graph, Category, Symbol, Relation
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

    async def run(self):
        async with self.wc:
            self.wc.ensure_branch(self.task.branch)
            self.wc.roll_back_changes('.')
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

                if task.plan is None:
                    await self.plan()
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

        for path in task.paths:
            full_path = os.path.join(wc.project_dir, path)
            parser_cls = detect_parser(full_path)
            parser = parser_cls()
            parser.cross_reference(graph, path)

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
        params = GenerationParams(max_tokens=1000, temperature=0.2, constraint=constraint)
        gen = Generation.new('find_relevant_symbols', C.SYSTEM_CODING_ASSISTANT, instruction, params)
        task.relevant_symbols_generation = gen
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            task.state = TaskState.FAILED
            task.error = f'Failed to find the relevant symbols:\n\n{gen.error}'
            return

        completion = gen.completions[0]

        names: Set[str] = set(json.loads(completion)['symbols'])
        # print(f'names = {names}')

        symbols = {symbol for symbol in task.code_map.symbols.values() if symbol.name in names and symbol.category != Category.IDENTIFIER}
        # print(f'symbols = {symbols}')

        paths: Set[str] = {
            path
            for path in task.paths
            if path in task.description
        }
        # print(f'paths = {paths}')

        dependent_symbols: Set[Symbol] = set()
        for symbol in symbols:
            # print(f'? symbol = {symbol}')
            for relation, used_by in task.code_map.iter_related(symbol):
                if relation == Relation.USED_BY:
                    # print(f'=> used_by = {used_by}')
                    dependent_symbols.add(used_by)
        # print(f'dependent_symbols = {dependent_symbols}')

        symbols.update(dependent_symbols)
        paths.update(symbol.path for symbol in symbols)
        # print(f'symbols = {symbols}')
        # print(f'paths = {paths}')

        if not symbols or not paths:
            task.state = TaskState.FAILED
            task.error = f'Could not narrow down the symbols and files to work on based on the task description'
            return

        task.relevant_symbols = sorted(symbol.id for symbol in symbols)
        task.sources = [
            Source.from_file(self.wc.project_dir, path)
            for path in paths
        ]

        relevant_symbol_ids = set(task.relevant_symbols)
        for source in task.sources:
            source_path = source.document.path
            relevant_blocks: list[Block] = []
            for symbol in task.code_map.symbols.values():
                if symbol.path != source_path:
                    continue
                if symbol.category not in (Category.INTERFACE, Category.CLASS, Category.STRUCT, Category.RECORD, Category.FUNCTION, Category.VARIABLE):
                    continue
                if relevant_symbol_ids & set(task.code_map.relations[symbol.id]):
                    relevant_blocks.append(symbol.block)

            if not relevant_blocks:
                source.relevant = Hunk.from_document(source.document, Block.from_range(0, 1))
            elif len(relevant_blocks) == 1:
                source.relevant = Hunk.from_document(source.document, relevant_blocks[0])
            else:
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

                hunks = [Hunk.from_document(source.document, b) for b in merged_blocks]
                patch = Patch.from_hunks(source.document, hunks)
                patch.merge_hunks()
                source.relevant = patch.hunks[0]

        task.state = TaskState.CODING

    async def plan(self):
        task = self.task
        task.planning_generations = []

        instruction = render_workflow_template(
            'plan',
            task=task,
        )
        params = GenerationParams(n=8, beam_search=True, max_tokens=1000, temperature=0.7)
        plan_gen = Generation.new('plan', C.SYSTEM_CODING_ASSISTANT, instruction, params)
        task.planning_generations.append(plan_gen)
        self.dump_task()
        await plan_gen.wait()
        self.dump_task()
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
                task.planning_generations.append(compare_gen)
                self.dump_task()
                await compare_gen.wait()
                self.dump_task()
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

    async def code_task(self):
        task = self.task

        if not task.sources:
            task.state = TaskState.FAILED
            task.error = f'No source files to change'
            return

        source_paths = {source.document.path for source in task.sources}

        instruction = render_workflow_template(
            'implement_task',
            task=task,
            source_paths=source_paths,
        )

        # Disabled due to https://github.com/outlines-dev/outlines/issues/680
        # Waiting on a fix or changing to a Lark grammar: https://github.com/outlines-dev/outlines/pull/676
        # existing_files_pattern = ''.join(
        #     rf'(Path: `{re.escape(source.document.path)}`\n\n```{re.escape(source.document.code_block_type)}\n(\n|[^`].*?\n)*```\n\n)?'
        #     for source in task.sources
        # )
        # new_files_pattern = rf'(New: `(.*?)`\n\n```([a-z]+)\n(\n|[^`].*?\n)*```\n\n)?'
        # pattern = rf'{existing_files_pattern}{new_files_pattern}{new_files_pattern}{new_files_pattern}'

        pattern = rf'(Path: `(.*?)`\n\n`{{3}}([a-z]+)\n(\n|[^`].*?\n)*`{{3}}\n+)+(New: `(.*?)`\n\n`{{3}}([a-z]+)\n(\n|[^`].*?\n)*`{{3}}\n+)*'

        constraint = Constraint.from_regex(pattern)
        params = GenerationParams(n=8, beam_search=True, temperature=0.2, constraint=constraint)
        gen = Generation.new('implement_task', C.SYSTEM_CODING_ASSISTANT, instruction, params)

        task.patch_generation = gen
        self.dump_task()
        await gen.wait()
        self.dump_task()

        if gen.state == GenerationState.FAILED:
            task.state = TaskState.FAILED
            task.error = f'Failed to implement the task'
            return

        task.integration_generations = []

        for i, completion in enumerate(gen.completions):
            print(f'Trying to apply change from completion {i}')
            error = await self.apply_code_changes(completion, source_paths)
            if not task.is_wip:
                return
            if not error:
                break
            self.wc.roll_back_changes('.')

        task.state = TaskState.TESTING

    async def apply_code_changes(self, completion: str, source_paths: Set[str]) -> str:
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

                modify = False
                create = False

                path = ''
                for k in range(i - 1, -1, -1):
                    line = completion_lines[k].strip()
                    if not line:
                        continue
                    modify = line.startswith('Path: `') and line.endswith('`')
                    create = line.startswith('New: `') and line.endswith('`')
                    if modify or create:
                        path = line.split(': `', 1)[1][:-1]
                    break

                if not path:
                    return f'Cannot find path line before completion code block (ignored): {i}:{j}'

                if modify and path not in source_paths:
                    print(f'WARN: The implementation wants to modify an unknown file (ignored): {path}')
                    continue

                if create and path in task.paths:
                    print(f'The implementation wants to create a file which already exists (ignored): {path}')
                    continue

                if path in paths_seen:
                    print(f'Ignoring repeated path: {path}')
                    continue

                paths_seen.add(path)

                full_path = os.path.join(self.wc.project_dir, path)

                code_lines = completion_lines[i + 1:j]
                code = join_lines(code_lines)

                if code.strip():
                    if modify:
                        print(f'Modify: {path}')
                        document = Document.from_file(self.wc.project_dir, path)
                        if len(pool) >= 16:
                            await pool.wait()
                        pool.run(self.reintegrate_code_change(document, code))
                    else:
                        print(f'Create: {path}')
                        write_text_file(full_path, code)
                    paths_to_stage.append(path)
                elif modify and os.path.exists(full_path):
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
        task.integration_generations.append(gen)

        self.dump_task()
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

    async def build_and_test_task(self):
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
