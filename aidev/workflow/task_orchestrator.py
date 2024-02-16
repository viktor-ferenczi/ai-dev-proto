import asyncio
from typing import Dict

from .model import Solution, Task, TaskState
from .task_processor import TaskProcessor
from ..common.async_helpers import AsyncPool
from ..common.config import C
from ..workflow.working_copy import WorkingCopy


class TaskOrchestrator:
    """Orchestrates tasks of a solution"""

    def __init__(self, solution: Solution):
        super().__init__()
        self.solution: Solution = solution
        self.wip_tasks: Dict[str, Task] = {}

        # FIXME: Support multiple folders per solution for parallel work
        self.working_copies = [
            WorkingCopy(solution.folder, solution.name)
        ]

        self.max_parallel_tasks: int = min(C.MAX_PARALLEL_TASKS, len(self.working_copies))

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
            if len(self.wip_tasks) >= self.max_parallel_tasks:
                break

            if not task.is_wip:
                continue

            if task.id in self.wip_tasks:
                continue

            print(f'Task continued: {task.id}')
            self.wip_tasks[task.id] = task
            pool.run(self.process_task(task))

    def start_new_tasks(self, pool: AsyncPool):
        for task in self.solution.tasks.values():
            if len(self.wip_tasks) >= self.max_parallel_tasks:
                break

            if task.state != TaskState.NEW:
                continue

            print(f'Task started: {task.id}')
            task.state = TaskState.PLANNING
            self.wip_tasks[task.id] = task
            pool.run(self.process_task(task))

    async def process_task(self, task: Task):
        working_copy = self.working_copies.pop()
        await TaskProcessor(self.solution, task, working_copy).run()
        self.working_copies.append(working_copy)
        del self.wip_tasks[task.id]
