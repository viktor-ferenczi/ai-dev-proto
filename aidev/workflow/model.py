from uuid import UUID, uuid1
from enum import Enum
from typing import Optional
from pydantic import BaseModel

from aidev.editing.model import Changeset, Document, Hunk
from aidev.engine.params import GenerationParams


class GenerationState(BaseModel):
    """
        Represents possible states of Generation
    """
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Generation(BaseModel):
    """
        Represents a single invocation of a Language Model (LLM), which may produce multiple completions (batch generation).

        Attributes:
        - state: GenerationState
            The state of the generation process. Possible values: PENDING, GENERATING, COMPLETED, FAILED.

        - system: str
            The system part of the prompt.

        - instruction: str
            The instruction part of the prompt.

        - params: GenerationParams
            Parameters to select a model and control the text generation.

        - completions: List[str]
            List of text completions once the LLM has finished generating.

        - error: Optional[str]
            Error message in the FAILED state. None if there is no error.

        Task types:
            First attempt of a top level task directly from ticket: id is set, parent and retried are None
            Retried top level task: id and retried are set, parent is None
            Sub-tasks: id is set, parent is set, retried is None
            Retried sub-task: id, parent and retried are all set

        Fields to index once stored in a database:
        - id
        - parent
        - retried
        - state

        """
    state: GenerationState
    system: str
    instruction: str
    params: GenerationParams
    completions: list[str]
    error: Optional[str]


class SourceState(Enum):
    """
        Represents possible states of Source
    """
    NEW = "NEW"
    RELEVANCE = "RELEVANCE"
    LOOKUP = "LOOKUP"
    IMPLEMENTATION = "IMPLEMENTATION"
    MODIFIED = "MODIFIED"


class Dependency(BaseModel):
    """
       Represents the definition of a dependency pulled from the code map.

       Attributes:
       - symbol: str
           The name of a symbol in the source code for which the dependency is pulled.

       - path: str
           The path of the source file from which the definition is pulled.

       - definition: str
           The definition of the dependency, such as enum, class, struct, method, etc.

        Remarks
        - The code map is a directed acyclic graph (DAG) cross-referencing the source code and updated as the  code
          changes (not detailed here).
        - The symbol is a unique identifier inside the source file, for example the name of an enum, class, struct or a
          method.
        - The definition may be shortened to contain only the parts relevant for the task at hand to save on context
          length.

    """
    symbol: str
    path: str
    definition: str


class Source(BaseModel):
    """
    Represents the full state of preparing and completing the corresponding task on a single source file.

    Attributes:
    - state: SourceState
        The current state of the source file, which can be NEW, RELEVANCE, LOOKUP, IMPLEMENTATION, MODIFIED, or FAILED.

    - document: Document
        The original source file contents.

    - relevant_code_generation: Optional[Generation]
        Request to find the relevant parts of code. Can be None if not applicable.

    - relevant_code_hunk: Optional[Hunk]
        The hunk containing all the code which may change. Can be None if not applicable.

    - dependency_generations: List[Generation]
        Iterative requests to find missing dependencies.

    - dependencies: List[Dependency]
        Dependencies retrieved from the code map.

    - implementation_generation: Optional[Generation]
        Request to actually implement the change. Can be None if not applicable.

    - changeset: Optional[Changeset]
        Hunks from the LLM generated implementation completion. Can be None if not applicable.

    - modified_document: Optional[Document]
        Source file contents with the changeset applied. Can be None if not applicable.

    - error: Optional[str]
        Error message in FAILED state. Can be None if the state is not FAILED.

    Remarks:
    - The optional fields are filled up as the state progresses and the information becomes available.
    - Dependencies are discovered iteratively and deduplicated after each step.
    - Configurable limits imposed on all generations. Once exceeded the source will fail.

    """
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
    """
    Represents constructive feedback on a FAILED or REJECTED task.
    It helps to avoid the same mistake in subsequent attempts to accomplish the same task (retries).

    Attributes:
    - critic: str
        Name or identifier of the LLM (Large Language Model) or human providing the criticism (free form).

    - criticism: str
        The criticism provided in Markdown format.

    """

    critic: str
    criticism: str


class TaskState:
    """
    Possible states of a Task.
    """
    NEW = "NEW"
    WIP = "WIP"
    REVIEW = "REVIEW"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class Task(BaseModel):
    """
        Full state of one attempt to implement a task described in an external ticket.

        Attributes:
        - id: UUID
            ID of the task

        - parent: Optional[str]
            ID of the parent task, used only for sub-tasks (defines a dependency tree).

        - retried: Optional[str]
            ID of the previous attempt to accomplish the same task (retry).

        - state: TaskState
            Current state of the task

        - ticket: str
            External reference, for example, a Gitlab ticket ID or URL.

        - branch: str
            Name of the Git branch to commit to, must be unique between active tasks.

        - description: str
            Task description copied from the ticket (Markdown formatted).

        - sources: List[Source]
            Source files that need to be modified, does not include dependencies from the code map.

        - pr: str
            Reference of the PR to review the changes committed to the branch.

        - feedbacks: List[Feedback]
            Extended by additional items on cloning the task for retry.

        - error: Optional[str]
            Error message in FAILED state.
    """

    id: UUID = uuid1()  # monotonically increasing, good for indexing
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
    """
       Full workflow state while working on tasks applicable to the solution with a VCS working copy in a folder.

       Attributes:
       - folder: str
           The path to the working copy folder.

       - tasks: Dict[str, Task]
           all tasks regardless of the state
    """
    folder: str
    tasks: dict[str, Task]
