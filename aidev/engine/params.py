from pydantic import BaseModel


class GenerationParams(BaseModel):
    number_of_completions: int = 1
    max_tokens: int = 256
    temperature: float = 0.2
    grammar: str = ''
