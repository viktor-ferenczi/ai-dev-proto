class Tokenizer:

    def count_tokens(self, text: str) -> int:
        raise NotImplementedError()


def get_tokenizer(model: str) -> Tokenizer:
    if model == 'openai':
        from .openai_tokenizer import OpenAITokenizer
        return OpenAITokenizer()
    if model == 'codellama':
        from .llama_tokenizer import LlamaTokenizer
        return LlamaTokenizer()
    if model == 'deepseek':
        from .deepseek_tokenizer import DeepSeekTokenizer
        return DeepSeekTokenizer()
