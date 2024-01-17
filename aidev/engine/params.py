from enum import Enum
from typing import Any

from pydantic import BaseModel


class GenerationParams(BaseModel):
    n: int = 1
    use_beam_search: bool = False
    max_tokens: int = 256
    # Keep the default temperature at zero, that's required when beam search is turned on
    temperature: float = 0.0


class ConstraintType(str, Enum):
    JSON_SCHEMA = 'JSON_SCHEMA'
    REGEX = 'REGEX'
    GRAMMAR = 'GRAMMAR'


class GenerationConstraint:
    def __init__(self, type: ConstraintType, value: Any):
        self.type = type
        self.value = value


class JsonSchemaConstraint(GenerationConstraint):
    def __init__(self, schema: Any) -> None:
        super().__init__(ConstraintType.JSON_SCHEMA, schema)


class RegexConstraint(GenerationConstraint):
    def __init__(self, regex_pattern: str) -> None:
        assert isinstance(regex_pattern, str)
        super().__init__(ConstraintType.REGEX, regex_pattern)


class GrammarConstraint(GenerationConstraint):
    def __init__(self, grammar: str) -> None:
        assert isinstance(grammar, str)
        super().__init__(ConstraintType.GRAMMAR, grammar)
