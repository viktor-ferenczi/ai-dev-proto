import asyncio
import os
import unittest

from aidev.engine.params import GenerationParams
from aidev.engine.vllm_engine import VllmEngine
from aidev.workflow.generation_orchestrator import GenerationOrchestrator
from aidev.workflow.model import Solution, Task, TaskState, Source
from aidev.thinking.model import GenerationState, Generation

SCRIPT_DIR = os.path.dirname(__file__)


class GenerationOrchestratorTest(unittest.IsolatedAsyncioTestCase):

    async def test_generations(self):
        solution = Solution.new('Test', os.path.dirname(__file__))

        generations: list[Generation] = []

        def create_generation():
            generation = Generation.new('', 'You are a helpful C# coding assistant.', '''
                    Write a C# 10 console program to print the integers from 1 to 10, each one on a separate line.
                    Write only the code and nothing else. Do not explain, do not add source code comments.
                ''', GenerationParams(max_tokens=150, temperature=0.2))
            generations.append(generation)
            return generation

        def create_source():
            source = Source.from_file(SCRIPT_DIR, __file__)
            source.relevant_generation = create_generation()
            source.patch_generation = create_generation()
            return source

        task = Task(
            id='Test-1',
            ticket='Ticket-1',
            description='description',
            branch='branch',
            state=TaskState.PLANNING,
            feedback_generation=create_generation(),
            sources=[create_source(), create_source()],
        )
        solution.tasks[task.id] = task

        self.assertEqual(5, len(generations))

        orchestrator = GenerationOrchestrator(solution)

        engine = VllmEngine()
        orchestrator.register_engine(engine)

        async def complete_task_when_generated():
            for _ in range(60):

                if any(g.state == GenerationState.FAILED for g in generations):
                    raise RuntimeError('One or more generations failed')

                if all(g.state == GenerationState.COMPLETED for g in generations):
                    task.state = TaskState.REVIEW
                    break

                await asyncio.sleep(0.5)

        await asyncio.wait([
            asyncio.create_task(orchestrator.run_until_complete()),
            asyncio.create_task(complete_task_when_generated()),
        ])

        self.assertEqual(TaskState.REVIEW, task.state)

        for generation in generations:
            self.assertEqual(GenerationState.COMPLETED, generation.state)
            self.assertEqual(1, len(generation.completions))
            self.assertTrue('WriteLine' in generation.completions[0])

        print(generations[0].model_dump_json(indent=2))
