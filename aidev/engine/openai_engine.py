import json
from typing import List, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from .engine import Engine
from .params import GenerationParams
from ..common.config import C
from ..tokenizer.tokenizer import get_tokenizer


class Usage(BaseModel):
    generations: int = 0
    completions: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def save(self, path: str):
        data = self.model_dump_json(indent=2)
        with open(path, 'wb') as f:
            json.dump(data, f)

    def load(self, path: str):
        with open(path, 'rb') as f:
            data = json.load(f)
        self.__dict__.update(data)


class OpenAIEngine(Engine):

    def __init__(self, base_url: str = '', api_key: str = '', model: str = '') -> None:
        super().__init__()
        self.base_url = base_url or C.OPENAI_BASE_URL
        self.api_key = api_key or C.OPENAI_KEY
        self.model = model or C.MODEL
        self.tokenizer = get_tokenizer(self.model)
        self.usage = Usage()

    def count_tokens(self, text: str) -> int:
        return self.tokenizer.count_tokens(text)

    async def generate(self, system: str, instruction: str, params: GenerationParams) -> List[str]:
        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        try:
            completion = await client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": instruction}
                ],
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
