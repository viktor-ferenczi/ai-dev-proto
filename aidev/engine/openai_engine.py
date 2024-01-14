from typing import List

from openai import AsyncOpenAI

from .engine import Engine
from .params import GenerationParams
from .usage import Usage
from ..common.config import C
from ..tokenizer.tokenizer import get_tokenizer


class OpenAIEngine(Engine):

    def __init__(self, model: str = '', base_url: str = '', api_key: str = '') -> None:
        super().__init__(model)

        self.base_url = base_url or C.OPENAI_BASE_URL
        self.api_key = api_key or C.OPENAI_KEY
        self.tokenizer = get_tokenizer(self.model)
        self.usage = Usage()

        self.max_context = C.CONTEXT_SIZE[self.model]
        self.optimal_parallel_sequences = C.OPTIMAL_PARALLEL_SEQUENCES[self.model]

    def count_tokens(self, text: str) -> int:
        return self.tokenizer.count_tokens(text)

    async def generate(self, system: str, instruction: str, params: GenerationParams) -> List[str]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": instruction}
        ]

        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        try:
            completion = await client.chat.completions.create(
                messages=messages,
                model=C.OPENAI_MODEL,
                max_tokens=params.max_tokens,
                temperature=params.temperature,
                n=params.number_of_completions,
            )
        finally:
            await client.close()

        self.usage.generations += 1
        self.usage.completions += len(completion.choices)
        self.usage.prompt_tokens += completion.usage.prompt_tokens
        self.usage.completion_tokens += completion.usage.completion_tokens

        assert len(completion.choices) == params.number_of_completions, (len(completion.choices), params.number_of_completions)
        return [choice.message.content for choice in completion.choices]
