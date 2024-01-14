from typing import List

from vllm_client import AsyncVllmClient, SamplingParams

from .engine import Engine
from .params import GenerationParams
from ..common.config import C
from ..common.util import get_prompt_template_for_model


class VllmEngine(Engine):

    def __init__(self, model: str = '', base_url: str = '') -> None:
        super().__init__(model)

        self.base_url = base_url or C.VLLM_BASE_URL

        self.max_context = C.CONTEXT_SIZE[self.model]
        self.optimal_parallel_sequences = C.OPTIMAL_PARALLEL_SEQUENCES[self.model]

        self.prompt_template = get_prompt_template_for_model(self.model)
        self.client = AsyncVllmClient(self.base_url)

    def count_tokens(self, text: str) -> int:
        return self.tokenizer.count_tokens(text)

    async def generate(self, system: str, instruction: str, params: GenerationParams) -> List[str]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": instruction}
        ]

        prompt = self.prompt_template.render(messages=messages)

        sampling_params = SamplingParams(
            n=params.number_of_completions,
            max_tokens=params.max_tokens,
            temperature=params.temperature,
        )

        full_completions = await self.client.generate(prompt, sampling_params)

        completions = []
        for full_completion in full_completions:
            assert full_completion.startswith(prompt), 'Completion does not start with the prompt'
            completions.append(full_completion[len(prompt):])

        self.usage.generations += 1
        self.usage.completions += len(completions)
        self.usage.prompt_tokens += self.count_tokens(prompt)
        self.usage.completion_tokens += sum((self.count_tokens(completion) for completion in completions), 0)

        return completions
