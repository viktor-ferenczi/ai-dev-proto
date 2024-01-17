from uuid import UUID, uuid1
from enum import Enum
from typing import Optional
from pydantic import BaseModel

from aidev.editing.model import Changeset, Document, Hunk
from aidev.engine.params import GenerationParams


class GenerationState(BaseModel):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Generation(BaseModel):
    state: GenerationState
    system: str
    instruction: str
    params: GenerationParams
    completions: list[str]
    error: Optional[str]


class SourceState(Enum):
    NEW = "NEW"
    RELEVANCE = "RELEVANCE"
    LOOKUP = "LOOKUP"
    IMPLEMENTATION = "IMPLEMENTATION"
    MODIFIED = "MODIFIED"


class Dependency(BaseModel):
    symbol: str
    path: str
    definition: str


class Source(BaseModel):
    state: SourceState
    document: Document
    relevant_code_generation: Optional[Generation]
    relevant_code_hunk: Optional[Hunk]
    dependency_generations: list[Generation]
    dependencies: list[Dependency]
    implementation_generation: Optional[Generation]
    changeset: Optional[Changeset]
    modified_document: Optional[Document]
    error: Optional[str]


class Feedback(BaseModel):
    critic: str
    criticism: str


class TaskState(Enum):
    NEW = "NEW"
    WIP = "WIP"
    REVIEW = "REVIEW"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class Task:
    id: UUID = uuid1() # monotonically increasing, good for indexing
    parent: Optional[str]
    retried: Optional[str]
    state: TaskState
    ticket: str
    branch: str
    description: str
    sources: list[Source]
    pr: str
    feedbacks: list[Feedback]
    error: Optional[str]


class Solution(BaseModel):
    folder: str
    tasks: dict[str, Task]
