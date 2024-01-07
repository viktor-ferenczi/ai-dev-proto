from transformers import AutoTokenizer

from .tokenizer import Tokenizer

DEEPSEEK_LLM_TOKENIZER = AutoTokenizer.from_pretrained('deepseek-ai/deepseek-llm-67b-chat')


class DeepSeekLlmTokenizer(Tokenizer):

    def count_tokens(self, text: str) -> int:
        return len(DEEPSEEK_LLM_TOKENIZER.encode(text))
