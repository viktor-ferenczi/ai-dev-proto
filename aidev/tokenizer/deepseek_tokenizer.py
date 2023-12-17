from transformers import AutoTokenizer

from .tokenizer import Tokenizer

DEEPSEEK_TOKENIZER = AutoTokenizer.from_pretrained('TheBloke/deepseek-coder-1.3b-base-AWQ')


class DeepSeekTokenizer(Tokenizer):

    def count_tokens(self, text: str) -> int:
        return len(DEEPSEEK_TOKENIZER.encode(text))
