from transformers import AutoTokenizer

from .tokenizer import Tokenizer

YI_TOKENIZER = AutoTokenizer.from_pretrained('01-ai/Yi-6B-Chat')


class YiTokenizer(Tokenizer):

    def count_tokens(self, text: str) -> int:
        return len(YI_TOKENIZER.encode(text))
