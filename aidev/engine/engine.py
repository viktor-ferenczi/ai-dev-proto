from logging import Logger
from typing import List, Optional

from .usage import Usage
from ..common.config import C
from ..engine.params import GenerationParams, GenerationConstraint
from ..tokenizer.tokenizer import get_tokenizer


class Engine:

    def __init__(self, model: str = '', logger: Optional[Logger] = None):
        self.max_context: int = 0
        self.optimal_parallel_sequences: int = 0

        self.model = model or C.MODEL
        if self.model not in C.MODEL_NAMES:
            raise ValueError(f'Unknown model: {model}; Valid model names: {", ".join(sorted(C.MODEL_NAMES.keys()))}')

        self.logger = logger

        self.tokenizer = get_tokenizer(self.model)
        self.usage = Usage()

    def count_tokens(self, text: str) -> int:
        raise NotImplementedError()

    async def generate(self,
                       system: str,
                       instruction: str,
                       params: GenerationParams,
                       constraint: Optional[GenerationConstraint] = None) -> List[str]:
        raise NotImplementedError()
