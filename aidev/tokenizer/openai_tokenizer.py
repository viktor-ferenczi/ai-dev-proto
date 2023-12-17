import tiktoken

from .tokenizer import Tokenizer

# The tokenizer used for both GPT 3.5 and 4
CL100K_BASE_ENCODING = tiktoken.get_encoding("cl100k_base")


class OpenAITokenizer(Tokenizer):

    def count_tokens(self, text: str) -> int:
        return len(CL100K_BASE_ENCODING.encode(text))
