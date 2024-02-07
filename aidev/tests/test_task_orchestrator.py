import asyncio
import unittest

from aidev.common.util import copy_directory
from aidev.engine.vllm_engine import VllmEngine
from aidev.tests.data import ORIGINAL_SOLUTION_DIR, OUTPUT_SOLUTION_DIR
from aidev.workflow.generation_orchestrator import GenerationOrchestrator
from aidev.workflow.model import Solution, Task, TaskState
from aidev.workflow.task_orchestrator import TaskOrchestrator


class TaskOrchestratorTest(unittest.IsolatedAsyncioTestCase):

    async def test_task(self):
        copy_directory(ORIGINAL_SOLUTION_DIR, OUTPUT_SOLUTION_DIR)

        task = Task(
            id='Test-1',
            ticket='Ticket-1',
            description='Instead of printing "Hello World", change the code to print the integers from 1 to 10, one on each line.',
            branch='no-git-repository-used',
        )

        solution = Solution.new('Test', OUTPUT_SOLUTION_DIR)
        solution.tasks[task.id] = task

        engine = VllmEngine()
        generation_orchestrator = GenerationOrchestrator(solution)
        generation_orchestrator.register_engine(engine)

        task_orchestrator = TaskOrchestrator(solution)

        await asyncio.wait([
            asyncio.create_task(generation_orchestrator.run_until_complete()),
            asyncio.create_task(task_orchestrator.run_until_complete()),
        ])

        if task.state == TaskState.FAILED:
            print(f'FAILED: {task.error}')

        self.assertEqual(TaskState.REVIEW, task.state)
        self.assertEqual(1, len(task.sources))

        source = task.sources[0]

        print('RELEVANT CODE:')
        for line in source.relevant.code_block_lines:
            print(line)
        print()

        print('IMPLEMENTATION:')
        implementation = source.implementation
        for line in implementation.code_block_lines:
            print(line)
        print()

        self.assertEqual(8, len(implementation.code_block_lines))
        self.assertTrue(any('WriteLine' in line for line in implementation.lines))
