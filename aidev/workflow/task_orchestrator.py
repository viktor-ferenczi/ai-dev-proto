import asyncio
import os
import traceback
from contextlib import asynccontextmanager
from typing import AsyncContextManager

from .model import Solution, Task, TaskState, Source, Generation, GenerationState, SourceState
from ..common.async_helpers import AsyncPool
from ..common.config import C
from ..common.util import render_workflow_template, regex_from_lines, extract_code_blocks, join_lines
from ..developer.project import Project
from ..editing.model import Patch
from ..engine.params import GenerationParams, Constraint

SYSTEM_CODING_ASSISTANT = '''\
You are a helpful coding assistant experienced in C#, .NET Core., HTML, JavaScript and Python.
'''


class TaskOrchestrator:
    """Orchestrates tasks of a solution"""

    def __init__(self, solution: Solution):
        super().__init__()
        self.solution: Solution = solution
        self.wip_tasks = {}
        self.max_parallel_tasks = C.MAX_PARALLEL_TASKS
        self.working_copy_lock = asyncio.Lock()

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
            if task.sources is None:
                await self.find_relevant_sources(task)
                if task.state != TaskState.WIP:
                    return

            assert task.sources, f'The task has no sources assigned: {task.id}'

            for source in task.sources:
                if source.state == SourceState.PENDING:
                    await self.process_source(task, source)
                    if source.state == SourceState.FAILED:
                        task.state = TaskState.FAILED
                        task.error = f'Source {source.document.path} failed: {source.error}'
                        return

            async with self.working_copy(task) as wc:
                await self.build_and_test(task, wc)
            if task.state != TaskState.WIP:
                return

            task.state = TaskState.REVIEW

        except Exception:
            task.state = TaskState.FAILED
            task.error = traceback.format_exc()

        finally:
            del self.wip_tasks[task.id]

    async def find_relevant_sources(self, task: Task):
        paths = list(self.solution.iter_relative_source_paths())
        instruction = render_workflow_template(
            'find_relevant_sources',
            paths=join_lines(['```'] + paths + ['```']),
            task_description=task.description,
        )

        constraint = Constraint.from_regex(f'```\n{regex_from_lines(paths)}```\n')
        params = GenerationParams(n=8, use_beam_search=True, max_tokens=4000, constraint=constraint)
        gen = Generation.new(SYSTEM_CODING_ASSISTANT, instruction, params)

        task.sources_generation = gen
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            task.state = TaskState.FAILED
            task.error = f'Failed to generate the list of relevant source files: {gen.error}'
            return

        for completion in gen.completions:
            lines = completion.strip().split('\n')
            if len(lines) > 2:
                break
        else:
            task.state = TaskState.FAILED
            task.error = f'Found no relevant source files'
            return

        assert lines[0] == '```'
        assert lines[-1] == '```'
        task.sources = [
            Source.from_path(os.path.join(self.solution.folder, path))
            for path in lines[1:-1]
        ]

    async def build_and_test(self, task: Task, wc: Project):
        error = wc.build()
        if error:
            task.state = TaskState.FAILED
            task.error = f'Failed to build:\n\n{error}'
            return

        error = wc.test()
        if error:
            task.state = TaskState.FAILED
            task.error = f'Failed to test:\n\n{error}'
            return

    async def process_source(self, task: Task, source: Source):
        if source.relevant is None:
            await self.find_relevant_code(task, source)
            if source.state != SourceState.PENDING or task.state != TaskState.WIP:
                return

        if source.dependencies is None:
            await self.find_dependencies(task, source)
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
            source=join_lines(source.document.get_code()),
            task_description=task.description,
        )

        code_block_type = source.document.doctype.code_block_type
        constraint = Constraint.from_regex(f'```{code_block_type}\n{regex_from_lines(source.document.lines)}```\n')
        params = GenerationParams(n=8, use_beam_search=True, max_tokens=4000, constraint=constraint)
        gen = Generation.new(SYSTEM_CODING_ASSISTANT, instruction, params)

        source.relevant_generation = gen
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            source.state = TaskState.FAILED
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
            source.state = TaskState.FAILED
            source.error = f'Found no relevant code lines'
            return

        patch.merge_hunks()
        source.relevant = patch.hunks[0]

    async def find_dependencies(self, task: Task, source: Source):
        # TODO
        source.dependencies = []

    async def implement_task(self, task: Task, source: Source):
        instruction = render_workflow_template(
            'implement_task',
            source=join_lines(source.relevant.get_code()),
            task_description=task.description,
        )

        code_block_type = source.document.doctype.code_block_type
        constraint = Constraint.from_regex(f'```{code_block_type}\n(.*?\n)*```\n')
        params = GenerationParams(n=8, use_beam_search=True, max_tokens=4000, constraint=constraint)
        gen = Generation.new(SYSTEM_CODING_ASSISTANT, instruction, params)

        source.patch_generation = gen
        await gen.wait()

        if gen.state == GenerationState.FAILED:
            source.state = TaskState.FAILED
            source.error = f'Failed to implement the task'
            return

        for completion in gen.completions:
            code_blocks = extract_code_blocks(completion)
            if len(code_blocks) != 1:
                continue
            replacement_lines = code_blocks[0].split('\n')
            break
        else:
            source.state = TaskState.FAILED
            source.error = f'Empty implementation'
            return

        source.relevant.replacement = replacement_lines
        source.patch = Patch.from_hunks(source.relevant.document, [source.relevant])
        source.implementation = source.patch.apply()
