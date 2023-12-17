from transformers import AutoTokenizer

from .tokenizer import Tokenizer

LLAMA_TOKENIZER = AutoTokenizer.from_pretrained('TheBloke/CodeLlama-7B-Instruct-fp16')


class LlamaTokenizer(Tokenizer):

    def count_tokens(self, text: str) -> int:
        return len(LLAMA_TOKENIZER.encode(text))
