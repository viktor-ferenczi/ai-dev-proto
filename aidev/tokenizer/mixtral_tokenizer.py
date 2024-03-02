from transformers import AutoTokenizer

from .tokenizer import Tokenizer

MIXTRAL_TOKENIZER = AutoTokenizer.from_pretrained('casperhansen/mixtral-instruct-awq')


class MixtralTokenizer(Tokenizer):

    def count_tokens(self, text: str) -> int:
        return len(MIXTRAL_TOKENIZER.encode(text))
