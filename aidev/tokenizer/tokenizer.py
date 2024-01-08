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

    if model == 'deepseek-coder':
        from .deepseek_coder_tokenizer import DeepSeekCoderTokenizer
        return DeepSeekCoderTokenizer()

    if model == 'deepseek-llm':
        from .deepseek_llm_tokenizer import DeepSeekLlmTokenizer
        return DeepSeekLlmTokenizer()

    if model == 'yi':
        from .yi_tokenizer import YiTokenizer
        return YiTokenizer()

    raise ValueError(f'Unknown model: {model}')
