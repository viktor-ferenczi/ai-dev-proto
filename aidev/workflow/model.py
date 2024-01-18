from uuid import UUID, uuid1
from enum import Enum
from typing import Optional
from pydantic import BaseModel

from aidev.editing.model import Changeset, Document, Hunk
from aidev.engine.params import GenerationParams


class GenerationState(BaseModel):
    """Represents possible states of Generation."""
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Generation(BaseModel):
    """Represents a single invocation of a Language Model (LLM), which may produce multiple completions (batch generation)."""

    state: GenerationState
    """The state of the generation process."""

    system: str
    """The system part of the prompt."""

    instruction: str
    """The instruction part of the prompt."""

    params: GenerationParams
    """Parameters to select a model and control the text generation."""

    completions: list[str]
    """List of text completions once the LLM has finished generating."""

    error: Optional[str]
    """Error message in the FAILED state. None if there is no error."""


class SourceState(Enum):
    """Represents possible states of Source."""
    NEW = "NEW"
    RELEVANCE = "RELEVANCE"
    LOOKUP = "LOOKUP"
    IMPLEMENTATION = "IMPLEMENTATION"
    MODIFIED = "MODIFIED"


class Dependency(BaseModel):
    """Represents the definition of a dependency pulled from the code map."""

    symbol: str
    """The name of a symbol in the source code for which the dependency is pulled."""

    path: str
    """The path of the source file from which the definition is pulled."""

    definition: str
    """The definition of the dependency, such as enum, class, struct, method, etc."""


class Source(BaseModel):
    """Represents the full state of preparing and completing the corresponding task on a single source file."""

    state: SourceState
    """The current state of the source file, which can be NEW, RELEVANCE, LOOKUP, IMPLEMENTATION, MODIFIED, or FAILED."""

    document: Document
    """The original source file contents."""

    relevant_code_generation: Optional[Generation]
    """Request to find the relevant parts of code. Can be None if not applicable."""

    relevant_code_hunk: Optional[Hunk]
    """The hunk containing all the code which may change. Can be None if not applicable."""

    dependency_generations: list[Generation]
    """Iterative requests to find missing dependencies."""

    dependencies: list[Dependency]
    """Dependencies retrieved from the code map."""

    implementation_generation: Optional[Generation]
    """Request to actually implement the change. Can be None if not applicable."""

    changeset: Optional[Changeset]
    """Hunks from the LLM generated implementation completion. Can be None if not applicable."""

    modified_document: Optional[Document]
    """Source file contents with the changeset applied. Can be None if not applicable."""

    error: Optional[str]
    """Error message in FAILED state. Can be None if the state is not FAILED."""


class Feedback(BaseModel):
    """Represents constructive feedback on a FAILED or REJECTED task."""

    critic: str
    """Name or identifier of the LLM (Large Language Model) or human providing the criticism (free form)."""

    criticism: str
    """The criticism provided in Markdown format."""


class TaskState:
    """Possible states of a Task."""
    NEW = "NEW"
    WIP = "WIP"
    REVIEW = "REVIEW"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class Task(BaseModel):
    """Full state of one attempt to implement a task described in an external ticket."""

    id: UUID = uuid1()  # monotonically increasing, good for indexing
    """ID of the task."""

    parent: Optional[str]
    """ID of the parent task, used only for sub-tasks (defines a dependency tree)."""

    retried: Optional[str]
    """ID of the previous attempt to accomplish the same task (retry)."""

    state: TaskState
    """Current state of the task."""

    ticket: str
    """External reference, for example, a Gitlab ticket ID or URL."""

    branch: str
    """Name of the Git branch to commit to, must be unique between active tasks."""

    description: str
    """Task description copied from the ticket (Markdown formatted)."""

    sources: list[Source]
    """Source files that need to be modified, does not include dependencies from the code map."""

    pr: str
    """Reference of the PR to review the changes committed to the branch."""

    feedbacks: list[Feedback]
    """Extended by additional items on cloning the task for retry."""

    error: Optional[str]
    """Error message in FAILED state."""


class Solution(BaseModel):
    """Full workflow state while working on tasks applicable to the solution with a VCS working copy in a folder."""

    folder: str
    """The path to the working copy folder."""

    tasks: dict[str, Task]
    """All tasks regardless of the state."""
