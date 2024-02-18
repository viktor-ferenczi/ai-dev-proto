from typing import Any, Optional, Dict

from pydantic import BaseModel

from ..common.util import SimpleEnum


class ConstraintType(SimpleEnum):
    JSON_SCHEMA = 'JSON_SCHEMA'
    REGEX = 'REGEX'
    GRAMMAR = 'GRAMMAR'


class Constraint(BaseModel):
    type: ConstraintType
    value: Any

    @classmethod
    def from_regex(cls, pattern: str):
        return cls(type=ConstraintType.REGEX, value=pattern)

    @classmethod
    def from_json_schema(cls, json_schema: Dict[str, Any]):
        return cls(type=ConstraintType.JSON_SCHEMA, value=json_schema)

    @classmethod
    def from_grammar(cls, grammar: str):
        return cls(type=ConstraintType.GRAMMAR, value=grammar)


class GenerationParams(BaseModel):
    n: int = 1
    use_beam_search: bool = False
    max_tokens: int = -1  # Negative number means let it generate up to the max context size of the model
    temperature: float = 0.0  # Keep the default temperature at zero, that's required when beam search is turned on
    constraint: Optional[Constraint] = None
