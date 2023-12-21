from typing import List

from ..engine.params import GenerationParams


class Engine:

    def __init__(self):
        self.max_context = 16384
        self.optimal_parallel_sequences = 16

    def count_tokens(self, text: str) -> int:
        raise NotImplementedError()

    async def generate(self, system: str, instruction: str, params: GenerationParams) -> List[str]:
        raise NotImplementedError()
