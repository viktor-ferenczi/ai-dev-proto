# API: https://github.com/openai/openai-python
import time

from openai import OpenAI, AsyncOpenAI
import unittest

from aidev.common.config import C
from aidev.common.async_helpers import AsyncPool
from aidev.common.util import set_slow_callback_duration_threshold
from aidev.tests.data import INSTRUCTION_DEDUPLICATE_FILES, crop_text, BOOK, QUESTIONS
from aidev.tokenizer import tokenizer


TOKENIZER = tokenizer.get_tokenizer(C.MODEL)
count_tokens = TOKENIZER.count_tokens


class SyncOpenAITest(unittest.TestCase):
    max_context = 16384

    def setUp(self):
        self.client = OpenAI(
            base_url=C.OPENAI_BASE_URL,
            api_key=C.OPENAI_KEY,
        )

    def tearDown(self):
        super().tearDown()
        self.client.close()

    def test_generation(self):
        started = time.perf_counter()
        completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."},
                {"role": "user", "content": 'How is an iterative quicksort algorithm implemented?'}
            ],
            model=C.OPENAI_MODEL,
            max_tokens=2000,
            temperature=0.2,
        )
        finished = time.perf_counter()
        duration = finished - started

        self.assertTrue(bool(completion))
        self.assertEqual(len(completion.choices), 1)

        token_count = completion.usage.completion_tokens
        print(f'Generated {token_count} tokens in {duration:.1f}s ({token_count / duration:.1f} tokens/s)')
        print(f'Output: {completion.choices[0].message.content}')

    def test_multiple(self):
        started = time.perf_counter()
        completion = self.client.chat.completions.create(
            n=10,
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."},
                {"role": "user", "content": 'How is an iterative quicksort algorithm implemented?'}
            ],
            model=C.OPENAI_MODEL,
            max_tokens=2000,
            temperature=0.7,
        )
        finished = time.perf_counter()
        duration = finished - started

        self.assertTrue(bool(completion))
        self.assertEqual(len(completion.choices), 10)

        token_count = completion.usage.completion_tokens
        print(f'Generated {token_count} tokens in {duration:.1f}s ({token_count / duration:.1f} tokens/s)')
        for i, choice in enumerate(completion.choices):
            print(f'Output {i}: {choice.message.content}')

    def test_coding(self):
        started = time.perf_counter()
        completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": C.SYSTEM_CODING_ASSISTANT},
                {"role": "user", "content": INSTRUCTION_DEDUPLICATE_FILES},
            ],
            model=C.OPENAI_MODEL,
            max_tokens=2000,
            temperature=0.2,
        )
        finished = time.perf_counter()
        duration = finished - started

        self.assertTrue(bool(completion.choices))

        token_count = completion.usage.completion_tokens
        print(f'Generated {token_count} tokens in {duration:.1f}s ({token_count / duration:.1f} tokens/s)')
        print('Output:')
        print(completion.choices[0].message.content.lstrip())

    def test_long_context(self):
        max_attempts = 5
        for size in (1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536, 81920, 98304, 131072, 163840, 196608, 229376, 262144):
            if size > self.max_context:
                break

            text = crop_text(count_tokens, BOOK, (size - 450) // 2)
            system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
            instruction = f'It is important to remember that the first key is "4242".\n\n{text}\n\nIt is important to remember that the second key is "1337".\n\n{text}\n\nWhat are the first and second keys? Give me only the two numbers. The keys are:'
            print(f'{size:>6d}: {count_tokens(system)} system + {count_tokens(instruction)} instruction + 400 completion')

            for attempt in range(max_attempts):

                completion = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": instruction}
                    ],
                    model=C.OPENAI_MODEL,
                    max_tokens=400,
                    temperature=0.7,
                )

                self.assertTrue(bool(completion))
                self.assertEqual(len(completion.choices), 1)

                content = completion.choices[0].message.content
                ok = True
                if '4242' not in content:
                    print(f'Attempt #{1 + attempt}: First key is missed')
                    ok = False
                if '1337' not in content:
                    print(f'Attempt #{1 + attempt}: Second key is missed')
                    ok = False

                if ok:
                    token_count = completion.usage.completion_tokens
                    self.assertTrue(token_count > 0, str(token_count))
                    break

            else:
                self.fail(f'Failed {max_attempts} attempts')


class AsyncOpenAITest(unittest.IsolatedAsyncioTestCase):
    max_parallel_connections = 16

    async def asyncSetUp(self):
        set_slow_callback_duration_threshold(C.SLOW_CALLBACK_DURATION_THRESHOLD)
        return await super().asyncSetUp()

    async def test_generation(self):
        self.token_count = 0

        started = time.perf_counter()
        async with AsyncPool() as pool:
            assert isinstance(pool, AsyncPool)
            for question in QUESTIONS:
                if len(pool) < self.max_parallel_connections:
                    pool.run(self.generate(question))
                else:
                    await pool.wait()
        finished = time.perf_counter()
        duration = finished - started

        print(f'TOTAL: Generated {self.token_count} tokens in {duration:.1f}s ({self.token_count / duration:.1f} tokens/s)')

    async def generate(self, question):
        client = AsyncOpenAI(
            base_url=C.OPENAI_BASE_URL,
            api_key=C.OPENAI_KEY,
        )
        try:
            completion = await client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."},
                    {"role": "user", "content": question}
                ],
                model=C.OPENAI_MODEL,
                max_tokens=100,
                temperature=0.2,
            )

            self.assertTrue(bool(completion.choices))
            self.token_count += completion.usage.completion_tokens

            print(f'Question: {question}')
            print(f'Answer: {completion.choices[0].message.content.lstrip()}')
            print('-' * 60)
        finally:
            await client.close()


if C.ENGINE != 'openai':
    del SyncOpenAITest
    del AsyncOpenAITest
