import json
from typing import List, Type, overload
from typing_extensions import Literal

from openai import AsyncOpenAI, RequestOptions
from openai._base_client import _AsyncStreamT
from openai._types import ResponseT, Body, RequestFiles
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


class CustomAsyncOpenAI(AsyncOpenAI):

    async def post(self, path: str, *, cast_to: Type[ResponseT], body: Body | None = None, files: RequestFiles | None = None, options: RequestOptions = {}, stream: bool = False, stream_cls: type[_AsyncStreamT] | None = None) -> ResponseT | _AsyncStreamT:
        grammar = options.get('extra_json', {}).pop('grammar', '')

        if grammar:
            body['grammar'] = grammar
            
        return await super().post(path, cast_to=cast_to, body=body, files=files, options=options, stream=stream, stream_cls=stream_cls)


class OpenAIEngine(Engine):

    def __init__(self, base_url: str = '', api_key: str = '', model: str = '') -> None:
        super().__init__()

        self.base_url = base_url or C.OPENAI_BASE_URL
        self.api_key = api_key or C.OPENAI_KEY
        self.model = model or C.MODEL
        self.tokenizer = get_tokenizer(self.model)
        self.usage = Usage()

        if self.model not in C._MODEL_NAMES:
            raise ValueError(f'Unknown model: {model}; Valid model names: {", ".join(sorted(C._MODEL_NAMES.keys()))}')

        self.max_context = C._CONTEXT_SIZE[self.model]
        self.optimal_parallel_sequences = C._OPTIMAL_PARALLEL_SEQUENCES[self.model]

    def count_tokens(self, text: str) -> int:
        return self.tokenizer.count_tokens(text)

    async def generate(self, system: str, instruction: str, params: GenerationParams) -> List[str]:
        client = CustomAsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
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
                extra_body={'grammar': params.grammar},
            )
        finally:
            await client.close()

        self.usage.generations += 1
        self.usage.completions += len(completion.choices)
        self.usage.prompt_tokens += completion.usage.prompt_tokens
        self.usage.completion_tokens += completion.usage.completion_tokens

        assert len(completion.choices) == params.number_of_completions, (len(completion.choices), params.number_of_completions)
        return [choice.message.content for choice in completion.choices]
