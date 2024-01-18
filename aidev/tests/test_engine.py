import json
import time

import unittest
from logging import DEBUG, INFO

from pydantic import BaseModel

from aidev.common.async_helpers import map_async, iter_async
from aidev.common.config import C
from aidev.common.util import set_slow_callback_duration_threshold, init_logger
from aidev.engine.engine import Engine
from aidev.engine.params import GenerationParams, JsonSchemaConstraint, RegexConstraint, GrammarConstraint
from aidev.engine.vllm_engine import VllmEngine
from aidev.tests.data import crop_text, BOOK, SYSTEM_CODING_ASSISTANT, INSTRUCTION_DEDUPLICATE_FILES, QUESTIONS

LOG_REQUESTS = False


class EngineTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        set_slow_callback_duration_threshold(C.SLOW_CALLBACK_DURATION_THRESHOLD)
        logger = init_logger(DEBUG if LOG_REQUESTS else INFO)
        self.engine: Engine = VllmEngine(logger=logger)  # OpenAIEngine()
        return await super().asyncSetUp()

    async def asyncTearDown(self):
        del self.engine
        return await super().asyncTearDown()

    def create_engine(self):
        raise NotImplementedError()

    async def test_single_completion(self):
        system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
        instruction = 'How is an iterative quicksort algorithm implemented?'
        params = GenerationParams(max_tokens=300)

        started = time.perf_counter()
        completions = await self.engine.generate(system, instruction, params)
        finished = time.perf_counter()
        duration = finished - started

        self.assertEqual(1, len(completions))
        completion = completions[0]
        token_count = self.engine.count_tokens(completion)

        usage = self.engine.usage
        self.assertEqual(1, usage.generations)
        self.assertEqual(1, usage.completions)
        self.assertTrue(-5 <= token_count - usage.completion_tokens <= 5)
        self.assertGreater(usage.prompt_tokens, 0)

        print(f'Generated {usage.completion_tokens} tokens in {duration:.1f}s ({usage.completion_tokens / duration:.1f} tokens/s)')
        print(f'Output:\n{completion}')

    async def test_multiple_completions(self):
        system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
        instruction = 'How is an iterative quicksort algorithm implemented?'
        params = GenerationParams(n=16, max_tokens=300, temperature=0.5)

        started = time.perf_counter()
        completions = await self.engine.generate(system, instruction, params)
        finished = time.perf_counter()
        duration = finished - started

        self.assertEqual(params.n, len(completions))

        usage = self.engine.usage
        print(f'Generated {usage.completion_tokens} tokens in {duration:.1f}s ({usage.completion_tokens / duration:.1f} tokens/s)')

        for index, completion in enumerate(completions):
            print(f'Output {index}:\n{completion}\n\n')
            self.assertTrue(bool(completion.strip()))

    async def test_coding(self):
        params = GenerationParams(max_tokens=2000, temperature=0.2)

        print('SYSTEM:')
        print(SYSTEM_CODING_ASSISTANT)
        print()

        print('INSTRUCTION:')
        print(INSTRUCTION_DEDUPLICATE_FILES)
        print()

        started = time.perf_counter()
        completions = await self.engine.generate(SYSTEM_CODING_ASSISTANT, INSTRUCTION_DEDUPLICATE_FILES, params)
        finished = time.perf_counter()
        duration = finished - started

        self.assertEqual(1, len(completions))

        completion = completions[0]

        usage = self.engine.usage
        print(f'Generated {usage.completion_tokens} tokens in {duration:.1f}s ({usage.completion_tokens / duration:.1f} tokens/s)')

        print(f'COMPLETION:\n{completion}')

        self.assertTrue(bool(completion.strip()))

    async def test_long_context(self):
        context_headroom_tokens = 100

        failed = 0
        max_attempts = 10

        for size in (1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536, 81920, 98304, 131072, 163840, 196608, 229376, 262144):
            if size > self.engine.max_context:
                break

            params = GenerationParams(max_tokens=100, temperature=0.5)

            system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
            system_tokens = self.engine.count_tokens(system)

            text = ''
            instruction = f'It is important to remember that the first key is "4242".\n\n{text}\n\nIt is important to remember that the second key is "1337".\n\n{text}\n\nWhat are the first and second keys? Give me only the two numbers. The keys are:'
            instruction_tokens = self.engine.count_tokens(instruction)

            text_tokens = (size - system_tokens - instruction_tokens - params.max_tokens - context_headroom_tokens) // 2
            text = crop_text(self.engine.count_tokens, BOOK, text_tokens)

            instruction = f'It is important to remember that the first key is "4242".\n\n{text}\n\nIt is important to remember that the second key is "1337".\n\n{text}\n\nWhat are the first and second keys? Give me only the two numbers. The keys are:'
            instruction_tokens = self.engine.count_tokens(instruction)

            expected_window_size = system_tokens + instruction_tokens + params.max_tokens + context_headroom_tokens

            print(f'{size:>6d}: {system_tokens} system + {instruction_tokens} instruction + {params.max_tokens} completion + {context_headroom_tokens} headroom = {expected_window_size} window size')

            for attempt in range(max_attempts):
                completions = await self.engine.generate(system, instruction, params)
                contents = completions[0]

                try:
                    self.assertTrue(bool(contents.strip()), 'Empty contents')
                    self.assertTrue('4242' in contents, 'First key is missed')
                    self.assertTrue('1337' in contents, 'Second key is missed')
                except AssertionError as e:
                    print(f'Attempt #{1 + attempt}: {e}')
                else:
                    print(f'{size:>6d}: Succeeded in {1 + attempt} attempt(s)')
                    break
            else:
                print(f'{size:>6d}: Failed')
                failed += 1

        self.assertEqual(0, failed, 'Some lengths failed')

    async def test_parallel_load(self):
        context_headroom_tokens = 100

        system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
        system_tokens = self.engine.count_tokens(system)

        async def generate(instruction: str) -> str:
            instruction_tokens = self.engine.count_tokens(instruction)
            max_tokens = self.engine.max_context - system_tokens - instruction_tokens - context_headroom_tokens
            params = GenerationParams(max_tokens=max_tokens, temperature=0.5)
            completions = await self.engine.generate(system, instruction, params)
            return completions[0]

        started = time.perf_counter()
        outputs = [completions[0] async for completions in map_async(generate, iter_async(QUESTIONS), max_tasks=self.engine.optimal_parallel_sequences)]
        finished = time.perf_counter()
        duration = finished - started

        self.assertEqual(len(QUESTIONS), len(outputs))

        for output in outputs:
            self.assertTrue(bool(output.strip()))

        usage = self.engine.usage
        print(f'Generated {usage.completion_tokens} tokens in {duration:.1f}s ({usage.completion_tokens / duration:.1f} tokens/s)')

    async def test_json_schema_constraint(self):
        class Fruit(BaseModel):
            kind: str
            color: str
            count: int
            weight: float
            sweet: bool

        schema = Fruit.model_json_schema()

        system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
        instruction = f"Write a JSON describing a random fruit. It must conform to the following JSON schema: {json.dumps(schema)}"

        params = GenerationParams(n=5, max_tokens=200, temperature=1.0)
        constraint = JsonSchemaConstraint(schema)
        completions = await self.engine.generate(system, instruction, params, constraint)

        self.assertEqual(len(completions), params.n)

        for completion in completions:
            print(completion)
            self.assertTrue(completion.startswith('{'))
            self.assertTrue(completion.endswith('}'))
            Fruit(**json.loads(completion))

    async def test_regex_constraint(self):
        system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
        instruction = f"Write down the first 10 prime numbers as a comma separated list, starting with 2."

        params = GenerationParams(max_tokens=50)
        constraint = RegexConstraint(r'\d+(\s*,\s*\d+)*\s*')
        completions = await self.engine.generate(system, instruction, params, constraint)

        self.assertEqual(len(completions), params.n)

        for completion in completions:
            self.assertEqual('2,3,5,7,11,13,17,19,23,29', completion.rstrip().replace(' ', ''))

    # Does not work, see: https://github.com/outlines-dev/outlines/issues/534
    async def test_grammar_constraint(self):
        self.fail('Disabled until the PR in outlines is merged')

        system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
        instruction = f"Write down the first 10 prime numbers as a comma separated list, starting with 2."

        params = GenerationParams(max_tokens=50)
        constraint = GrammarConstraint(r'''\
?start: DIGIT+ ( "," DIGIT+ )* _WS?
%import common.DIGIT
%import common.WS -> _WS
''')
        completions = await self.engine.generate(system, instruction, params, constraint)

        self.assertEqual(len(completions), params.n)

        for completion in completions:
            self.assertEqual('2,3,5,7,11,13,17,19,23,29', completion.rstrip().replace(' ', ''))
