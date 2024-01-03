import time

from openai import OpenAI

from aidev.common.config import C

client = OpenAI(
    base_url=C.OPENAI_BASE_URL,
    api_key=C.OPENAI_KEY,
)

started = time.perf_counter()
completion = client.chat.completions.create(
    messages=[
        {"role": "system", "content": "You are a helpful AI coding assistant. You give concise answers."},
        {"role": "user", "content": 'How is an iterative quicksort algorithm implemented?'}
    ],
    model=C.OPENAI_MODEL,
    max_tokens=1000,
    temperature=0.2,
)

finished = time.perf_counter()
duration = finished - started

assert bool(completion)
assert len(completion.choices) == 1

token_count = completion.usage.completion_tokens
print(f'Generated {token_count} tokens in {duration:.1f}s ({token_count / duration:.1f} tokens/s)')
print(f'Output: {completion.choices[0].message.content}')
