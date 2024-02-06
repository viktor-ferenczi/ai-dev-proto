import asyncio
import os
import traceback
from contextlib import asynccontextmanager
from typing import AsyncContextManager, Set

from .model import Solution, Task, TaskState, Source, Generation, GenerationState, SourceState, Feedback
from ..common.async_helpers import AsyncPool
from ..common.config import C
from ..common.util import render_workflow_template, regex_from_lines, extract_code_blocks, join_lines, replace_tripple_backquote, write_text_file, render_markdown_template
from ..developer.project import Project
from ..editing.model import Patch
from ..engine.params import GenerationParams, Constraint

SYSTEM_CODING_ASSISTANT = '''\
You are a helpful coding assistant experienced in C#, .NET Core., HTML, JavaScript and Python.
'''

SCRIPT_DIR = os.path.normpath(os.path.dirname(__file__))
DOCS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, 'docs'))


class TaskOrchestrator:
    """Orchestrates tasks of a solution"""

    def __init__(self, solution: Solution):
        super().__init__()
        self.solution: Solution = solution
        self.wip_tasks: dict[str, Task] = {}
        self.max_parallel_tasks: int = C.MAX_PARALLEL_TASKS
        self.working_copy_lock: asyncio.Lock = asyncio.Lock()
        self.temperature: float = 0.2

    @asynccontextmanager
    async def working_copy(self, task: Task) -> AsyncContextManager[Project]:
        # FIXME: Multiple folder support with a semaphore
        project = Project(self.solution.folder, self.solution.name)
        await self.working_copy_lock.acquire()
        try:
            if project.has_changes():
                raise IOError(f'The working copy folder has changes: {project.project_dir}')
            project.ensure_branch(task.branch)
            yield project
        finally:
            project.roll_back_changes('.')
            self.working_copy_lock.release()

    async def run_until_complete(self):
        async with AsyncPool() as pool:
            assert isinstance(pool, AsyncPool)
            while self.solution.has_any_tasks_remaining:
                if len(self.wip_tasks) < self.max_parallel_tasks:
                    self.pick_up_running_tasks(pool)
                    self.start_new_tasks(pool)

                if len(pool) >= self.max_parallel_tasks:
                    await pool.wait()
                else:
                    # FIXME: Polling loop, should listen on the relevant changes instead
                    await asyncio.sleep(0.5)

    def pick_up_running_tasks(self, pool: AsyncPool):
        for task in self.solution.tasks.values():
            if task.state == TaskState.WIP:
                if task.id not in self.wip_tasks:
                    self.wip_tasks[task.id] = task
                    pool.run(self.process_task(task))
                    if len(self.wip_tasks) == self.max_parallel_tasks:
                        return

    def start_new_tasks(self, pool: AsyncPool):
        for task in self.solution.tasks.values():
            if task.state == TaskState.NEW:
                task.state = TaskState.WIP
                self.wip_tasks[task.id] = task
                pool.run(self.process_task(task))
                if len(self.wip_tasks) == self.max_parallel_tasks:
                    return

    async def process_task(self, task: Task):
        try:
            self.dump_task(task)

            if task.sources is None:
                await self.find_relevant_sources(task)
                if task.state != TaskState.WIP:
                    return

            self.dump_task(task)

            if not task.sources:
                task.state = TaskState.FAILED
                task.error = f'Found no relevant source files for this task'
                return

            self.dump_task(task)

            async with AsyncPool() as pool:
                for source in task.sources:
                    pool.run(self.process_source(task, source))

                while pool:
                    await pool.wait()
                    self.dump_task(task)

            failed_sources = []
            for source in task.sources:
                if source.state == SourceState.FAILED:
                    failed_sources.append(source)
            if failed_sources:
                task.state = TaskState.FAILED
                task.error = join_lines(
                    ['Failed to process source file(s):'] +
                    [source.document.path for source in failed_sources]
                )
                return

            self.dump_task(task)

            assert all(source.state in (SourceState.COMPLETED, SourceState.SKIP) for source in task.sources), 'Invalid source states'

            if not any(source.state == SourceState.COMPLETED for source in task.sources):
                task.state = TaskState.FAILED
                task.error = f'No changes made to any of the source files'
                return

            async with self.working_copy(task) as wc:
                assert isinstance(wc, Project)

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

                wc.commit(task.id)

            task.state = TaskState.REVIEW

        except Exception:
            task.state = TaskState.FAILED
            task.error = traceback.format_exc()
            print(f'Task {task.id} failed with an unexpected error:')
            print(task.error)

        finally:
            self.dump_task(task)
            del self.wip_tasks[task.id]

    def dump_task(self, task: Task) -> None:
        dir_path = os.path.join(self.solution.folder, '.aidev', 'tasks')
        os.makedirs(dir_path, exist_ok=True)
        json_path = os.path.join(dir_path, f'{task.id}.json')
        write_text_file(json_path, task.model_dump_json(indent=2))

        os.makedirs(DOCS_DIR, exist_ok=True)
        md_path = os.path.join(DOCS_DIR, f'{task.id}.json')
        write_text_file(md_path, render_markdown_template('task', task=task))

    async def find_relevant_sources(self, task: Task):
        async with self.working_copy(task) as wc:
            assert isinstance(wc, Project)
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
        ]
        if not paths:
            task.state = TaskState.FAILED
            task.error = 'No source files in solution'
            return

        if len(paths) == 1:
            source = Source.from_file(self.solution.folder, paths[0])
            task.sources = [source]
            return

        task.source_selection_generations = []

        chunk_size: int = 20
        selected_paths: Set[str] = set()
        for i in range(0, len(paths), chunk_size):
            chunk = paths[i:i + chunk_size]

            gen = await self.find_relevant_sources_in_chunk(task, chunk, 2)
            if gen.state == GenerationState.FAILED:
                task.state = TaskState.FAILED
                task.error = f'Failed to generate the list of relevant source files:\n\n{gen.error}'
                return

            for completion in gen.completions:
                selected_paths.update(completion.strip().split('\n')[1:-1])

        gen = await self.find_relevant_sources_in_chunk(task, sorted(selected_paths), 4)
        selected_paths = set()
        for completion in gen.completions:
            selected_paths |= set(completion.strip().split('\n')[1:-1])

        if not selected_paths:
            task.state = TaskState.FAILED
            task.error = f'Found no relevant source files'
            return

        task.sources = [
            Source.from_file(self.solution.folder, path)
            for path in sorted(selected_paths)
        ]

    async def find_relevant_sources_in_chunk(self, task: Task, chunk: list[str], n: int) -> Generation:
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

    async def process_source(self, task: Task, source: Source):
        if source.relevant is None:
            await self.find_relevant_code(task, source)
            if source.state != SourceState.PENDING or task.state != TaskState.WIP:
                return

        if source.implementation is None:
            await self.implement_task(task, source)
            if source.state != SourceState.PENDING or task.state != TaskState.WIP:
                return

        source.state = SourceState.COMPLETED

    async def find_relevant_code(self, task: Task, source: Source):
        instruction = render_workflow_template(
            'find_relevant_code',
            source=source.document.code_block,
            task_description=task.description,
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

    async def implement_task(self, task: Task, source: Source):
        instruction = render_workflow_template(
            'implement_task',
            source=source.relevant.code_block,
            task_description=task.description,
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
