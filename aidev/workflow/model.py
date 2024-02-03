import asyncio
import os
from traceback import format_exc
from typing import Optional, Iterable
from pydantic import BaseModel

from ..common.config import C
from ..common.util import SimpleEnum
from ..editing.model import Patch, Document, Hunk
from ..engine.engine import Engine
from ..engine.params import GenerationParams


class GenerationState(str, SimpleEnum):
    """Represents possible states of Generation"""
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Generation(BaseModel):
    """Represents a single invocation of a Language Model (LLM), which may produce multiple completions (batch generation)"""

    state: GenerationState
    """The state of the generation process"""

    system: str
    """The system part of the prompt"""

    instruction: str
    """The instruction part of the prompt"""

    params: GenerationParams
    """Parameters to select a model and control the text generation"""

    completions: Optional[list[str]] = None
    """List of text completions once the LLM has finished generating"""

    error: Optional[str] = None
    """Error message in FAILED state"""

    @classmethod
    def new(cls, system: str, instruction: str, params: GenerationParams) -> 'Generation':
        return cls(
            state=GenerationState.PENDING,
            system=system,
            instruction=instruction,
            params=params,
            completions=[],
            error=None,
        )

    @property
    def is_finished(self) -> bool:
        return self.state in (GenerationState.COMPLETED, GenerationState.FAILED)

    def can_run_on(self, engine: Engine):
        tokens_can_fit = self.params.max_tokens <= engine.max_context
        constraint_is_supported = (
                self.params.constraint is None or
                self.params.constraint.type in engine.supported_constraint_types
        )
        return tokens_can_fit and constraint_is_supported

    async def run_on(self, engine: Engine):
        self.state = GenerationState.GENERATING
        try:
            self.completions = await engine.generate(self.system, self.instruction, self.params)
        except Exception:
            self.state = GenerationState.FAILED
            self.error = format_exc()
        else:
            self.state = GenerationState.COMPLETED

    async def wait(self):
        # FIXME: Replace with waiting on a state change async event
        while not self.is_finished:
            await asyncio.sleep(0.2)


class SourceState(str, SimpleEnum):
    """Represents possible states of Source"""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Dependency(BaseModel):
    """Represents the definition of a dependency pulled from the code map"""

    symbol: str
    """The name of a symbol in the source code for which the dependency is pulled"""

    path: str
    """The path of the source file from which the definition is pulled"""

    definition: str
    """The definition of the dependency, such as enum, class, struct, method, etc"""


class Source(BaseModel):
    """Represents the full state of preparing and completing the corresponding task on a single source file"""

    state: SourceState
    """The current state of the source file, which can be NEW, RELEVANCE, LOOKUP, IMPLEMENTATION, MODIFIED, or FAILED"""

    document: Document
    """The original source file contents"""

    relevant_generation: Optional[Generation] = None
    """Request to find the relevant parts of code"""

    relevant: Optional[Hunk] = None
    """Relevant part of the code"""

    dependency_generations: Optional[list[Generation]] = None
    """Iterative requests to find missing dependencies"""

    dependencies: Optional[list[Dependency]] = None
    """Dependencies retrieved from the code map"""

    patch_generation: Optional[Generation] = None
    """Request to actually implement the change"""

    patch: Optional[Patch] = None
    """Hunks from the LLM generated implementation completion"""

    implementation: Optional[Document] = None
    """Source file contents with the implementation (patch) applied"""

    error: Optional[str] = None
    """Error message in FAILED state"""

    @classmethod
    def from_path(cls, path: str):
        return cls(
            state=SourceState.PENDING,
            document=Document.from_file(path),
        )

    def iter_generations(self) -> Iterable[Generation]:
        if self.state != 'PENDING':
            return

        if self.relevant_generation is not None:
            yield self.relevant_generation

        if self.dependency_generations is not None:
            yield from self.dependency_generations

        if self.patch_generation is not None:
            yield self.patch_generation


class Feedback(BaseModel):
    """Represents constructive feedback on a FAILED or REJECTED task"""

    critic: str
    """Name or identifier of the LLM (Large Language Model) or human providing the criticism (free form)"""

    criticism: str
    """The criticism provided in Markdown format"""


class TaskState(str, SimpleEnum):
    """Possible states of a Task"""
    NEW = "NEW"
    WIP = "WIP"
    REVIEW = "REVIEW"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class Task(BaseModel):
    """Full state of one attempt to implement a task described in an external ticket"""

    id: str
    """ID of the task"""

    ticket: str
    """External reference, for example, a Gitlab ticket ID or URL"""

    description: str
    """Task description copied from the ticket (Markdown formatted)"""

    branch: str
    """Name of the Git branch to commit to, must be unique between active tasks"""

    parent: Optional[str] = None
    """ID of the parent task, used only for sub-tasks (defines a dependency tree)"""

    retried: Optional[str] = None
    """ID of the previous attempt to accomplish the same task (retry)"""

    state: TaskState = TaskState.NEW
    """Current state of the task"""

    sources_generation: Optional[Generation] = None
    """Request to find the relevant source code files"""

    sources: Optional[list[Source]] = None
    """Source files that need to be modified, does not include dependencies from the code map"""

    pr: Optional[str] = None
    """Reference of the PR to review the changes committed to the branch"""

    feedbacks: Optional[list[Feedback]] = None
    """Extended by additional items on cloning the task for retry"""

    error: Optional[str] = None
    """Error message in FAILED state"""

    @property
    def is_remaining(self) -> bool:
        return self.state in (TaskState.NEW, TaskState.WIP)

    def iter_generations(self) -> Iterable[Generation]:
        if self.state != 'WIP':
            return

        if self.sources_generation is not None:
            yield self.sources_generation

        if self.sources is not None:
            for source in self.sources:
                assert isinstance(source, Source)
                yield from source.iter_generations()


class Solution(BaseModel):
    """Full workflow state while working on tasks applicable to the solution with a VCS working copy in a folder"""

    name: str
    """Name of the solution, also used as project name in SonarQube"""

    # FIXME: Implement multiple working copy folders to support parallel build and testing
    folder: str
    """Working copy folder"""

    tasks: dict[str, Task]
    """All tasks by ID regardless of their state"""

    @classmethod
    def new(cls, name: str, folder: str) -> 'Solution':
        return cls(name=name, folder=folder, tasks={})

    @property
    def has_any_tasks_remaining(self) -> bool:
        return any(task.is_remaining for task in self.tasks.values())

    def iter_generations(self) -> Iterable[Generation]:
        for task in self.tasks.values():
            assert isinstance(task, Task)
            yield from task.iter_generations()

    def iter_relative_source_paths(self) -> Iterable[str]:
        relative_path_start = len(self.folder) + 1
        source_extensions = set(C.DOCTYPE_BY_EXTENSION)
        for dirpath, dirnames, filenames in os.walk(self.folder):
            for filename in filenames:
                ext = filename.rsplit('.', 1)[-1].lower()
                if ext in source_extensions:
                    yield os.path.join(dirpath, filename)[relative_path_start:]
