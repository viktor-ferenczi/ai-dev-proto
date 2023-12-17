from typing import List

from openai import AsyncOpenAI

from .engine import Engine
from .params import GenerationParams
from ..common.config import C
from ..tokenizer.tokenizer import get_tokenizer


class OpenAIEngine(Engine):

    def __init__(self, base_url: str = '', api_key: str = '', model: str = '') -> None:
        super().__init__()
        self.base_url = base_url or C.AIDEV_OPENAI_BASE_URL
        self.api_key = api_key or C.AIDEV_OPENAI_KEY
        self.model = model or C.AIDEV_MODEL
        self.tokenizer = get_tokenizer(self.model)

    def count_tokens(self, text: str) -> int:
        return self.tokenizer.count_tokens(text)

    async def generate(self, system: str, instruction: str, params: GenerationParams) -> List[str]:
        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

        completion = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": instruction}
            ],
            model=C.AIDEV_OPENAI_MODEL,
            max_tokens=params.max_tokens,
            temperature=params.temperature,
            n=params.number_of_completions,
        )

        assert len(completion.choices) == params.number_of_completions, (len(completion.choices), params.number_of_completions)
        return [choice.message.content for choice in completion.choices]
