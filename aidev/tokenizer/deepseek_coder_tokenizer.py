from transformers import AutoTokenizer

from .tokenizer import Tokenizer

DEEPSEEK_CODER_TOKENIZER = AutoTokenizer.from_pretrained('TheBloke/deepseek-coder-1.3b-base-AWQ')


class DeepSeekCoderTokenizer(Tokenizer):

    def count_tokens(self, text: str) -> int:
        return len(DEEPSEEK_CODER_TOKENIZER.encode(text))
