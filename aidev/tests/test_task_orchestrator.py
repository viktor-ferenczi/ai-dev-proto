import asyncio
import os
import unittest

from aidev.common.util import copy_directory
from aidev.engine.vllm_engine import VllmEngine
from aidev.workflow.generation_orchestrator import GenerationOrchestrator
from aidev.workflow.model import Solution, Task, TaskState
from aidev.workflow.task_orchestrator import TaskOrchestrator

SCRIPT_DIR = os.path.normpath(os.path.dirname(__file__))
SOLUTIONS_DIR = os.path.join(SCRIPT_DIR, 'solutions')
HELLO_WORLD_DIR = os.path.join(SOLUTIONS_DIR, 'HelloWorld')
ORIGINAL_SOLUTION_DIR = os.path.join(HELLO_WORLD_DIR, 'original')
OUTPUT_SOLUTION_DIR = os.path.join(HELLO_WORLD_DIR, 'output')


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
        for line in source.relevant.get_code():
            print(line)
        print()

        print('IMPLEMENTATION:')
        implementation = source.implementation
        for line in implementation.get_code():
            print(line)
        print()

        self.assertEqual(9, len(implementation.get_code()))
        self.assertTrue(any('WriteLine' in line for line in implementation.lines))
