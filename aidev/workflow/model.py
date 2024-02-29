import os
from asyncio import Event
from traceback import format_exc
from typing import Optional, Iterable, Dict, List, Set
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict

from ..code_map.model import CodeMap
from ..common.config import C
from ..common.util import SimpleEnum
from ..editing.model import Hunk
from ..engine.engine import Engine
from ..engine.params import GenerationParams


class GenerationState(SimpleEnum):
    """Represents possible states of Generation"""
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Generation(BaseModel):
    """Represents a single invocation of a Language Model (LLM), which may produce multiple completions (batch generation)"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    """Unique ID of this generation"""

    label: str
    """Label to identify the role of the generation in the thinking structure"""

    state: GenerationState
    """The state of the generation process"""

    system: str
    """The system part of the prompt"""

    instruction: str
    """The instruction part of the prompt"""

    params: GenerationParams
    """Parameters to select a model and control the text generation"""

    completions: Optional[List[str]] = None
    """List of text completions once the LLM has finished generating"""

    error: Optional[str] = None
    """Error message in FAILED state"""

    finish_event: Event = Field(exclude=True, default_factory=lambda: Event())
    """Event triggered when the generation is finished"""

    @classmethod
    def new(cls, label: str, system: str, instruction: str, params: GenerationParams) -> 'Generation':
        return cls(
            id=str(uuid4()),
            label=label,
            state=GenerationState.PENDING,
            system=system,
            instruction=instruction.rstrip(),
            params=params,
            completions=[],
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
        try:
            print(f'Starting generation: {self.label}')
            self.completions = await engine.generate(self.system, self.instruction, self.params)
        except Exception:
            self.state = GenerationState.FAILED
            self.error = format_exc()
            print(f'Failed generation: {self.label}')
            print(self.error)
        else:
            print(f'Finished generation: {self.label}')
            self.state = GenerationState.COMPLETED
            self.finish_event.set()

    async def wait(self):
        await self.finish_event.wait()


class Feedback(BaseModel):
    """Represents constructive feedback on a FAILED or REJECTED task"""

    critic: str
    """Name or identifier of the LLM (Large Language Model) or human providing the criticism (free form)"""

    criticism: str
    """The criticism provided in Markdown format"""


class TaskState(SimpleEnum):
    """Possible states of a Task"""
    NEW = "NEW"
    PARSING = "PARSING"
    PLANNING = "PLANNING"
    CODING = "CODING"
    REVIEW = "REVIEW"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


TASK_WIP_STATES = (
    TaskState.PARSING,
    TaskState.PLANNING,
    TaskState.CODING,
)

TASK_START_STATE = TASK_WIP_STATES[0]


class Task(BaseModel):
    """Full state of one attempt to implement a task described in an external ticket"""

    id: str
    """ID of the task"""

    ticket: str
    """External reference, for example, a Gitlab ticket ID or URL"""

    branch: str
    """Name of the Git branch to commit to, must be unique between active tasks"""

    description: str
    """Task description copied from the ticket (Markdown formatted)"""

    state: TaskState = TaskState.NEW
    """Current state of the task"""

    attempt: int = 0
    """Attempt index, valid in work-in-progress states"""

    commit_hash: Optional[str] = None
    """Git commit hash the work is based on when the task is started"""

    paths: Optional[List[str]] = None
    """Solution relative paths of all source files in the solution which may be considered when the task is started"""

    code_map: Optional[CodeMap] = None
    """Code map constructed from parsing all the source files when the task is started"""

    relevant_symbols: Optional[Set[str]] = None
    """IDs of the relevant symbols required to work on the task"""

    relevant_paths: Optional[List[str]] = None
    """List of relative source paths of the relevant source files"""

    relevant_hunks: Optional[List[Hunk]] = None
    """List of hunks with the relevant parts of the source files"""

    plan: Optional[str] = None
    """Step-by-step plan to implement the task"""

    pr: Optional[str] = None
    """Reference of the PR to review the changes committed to the branch"""

    generations: Optional[List[Generation]] = None
    """Text generation requests used while working on the task"""

    error: Optional[str] = None
    """Error message in FAILED state"""

    @property
    def is_wip(self) -> bool:
        return self.state in TASK_WIP_STATES

    @property
    def is_remaining(self) -> bool:
        return self.state == TaskState.NEW or self.is_wip

    def iter_generations(self) -> Iterable[Generation]:
        if self.is_wip and self.generations:
            yield from self.generations


class Solution(BaseModel):
    """Full workflow state while working on tasks applicable to the solution with a VCS working copy in a folder"""

    name: str
    """Name of the solution, also used as project name in SonarQube"""

    # TODO: Introduce multiple working copies
    folder: str
    """Working copy folder"""

    tasks: Dict[str, Task]
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
                    yield os.path.join(dirpath, filename)[relative_path_start:].replace('\\', '/')
