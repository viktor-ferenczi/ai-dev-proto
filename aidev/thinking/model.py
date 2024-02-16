import asyncio
from traceback import format_exc
from typing import Optional, Dict, Iterable
from uuid import uuid4

from pydantic import BaseModel

from ..common.util import SimpleEnum
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

    completions: Optional[list[str]] = None
    """List of text completions once the LLM has finished generating"""

    error: Optional[str] = None
    """Error message in FAILED state"""

    @classmethod
    def new(cls, label: str, system: str, instruction: str, params: GenerationParams) -> 'Generation':
        return cls(
            id=str(uuid4()),
            label=label,
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
        print('Starting generation')
        try:
            self.completions = await engine.generate(self.system, self.instruction, self.params)
        except Exception:
            print('Failed generation')
            self.state = GenerationState.FAILED
            self.error = format_exc()
        else:
            print('Finished generation')
            self.state = GenerationState.COMPLETED

    async def wait(self):
        # FIXME: Replace with waiting on a state change async event
        while not self.is_finished:
            await asyncio.sleep(0.2)


class Connection(SimpleEnum):
    """Connection between generations of structured thinking
    """
    RETRY = 'RETRY'
    """Retry of a generation with invalid result"""

    CONSEQUENCE = 'CONSEQUENCE'
    """Consequence of reasons"""

    COMBINATION = 'COMBINATION'
    """Combining facts"""


class Thinking(BaseModel):
    """Structured thinking as a graph of connected generations
    """

    generations: Dict[str, Generation]
    """Generations (graph nodes)"""

    connections: Dict[str, Dict[str, Connection]]
    """Connections between generations (graph edges)"""

    first_generation_id: Optional[str] = None
    """First generation (root)"""

    concluding_id: Optional[str] = None
    """Concluding generation ID"""

    conclusion_index: Optional[int] = None
    """Index of the conclusion (accepted completion) in the concluding generation"""

    @property
    def conclusion(self) -> Optional[str]:
        """Final completion if any"""
        if self.concluding_id is None:
            return None
        concluding_generation = self.generations[self.concluding_id]
        return concluding_generation.completions[self.conclusion_index]

    @classmethod
    def new(cls) -> 'Thinking':
        return cls(generations={}, connections={})

    def iter_generations(self) -> Iterable[Generation]:
        yield from self.generations.values()

    def iter_leaves(self) -> Iterable[Generation]:
        for id, generation in self.generations.items():
            if id not in self.connections:
                yield generation

    def start(self, generation: Generation):
        if self.first_generation_id is not None:
            raise ValueError(f'Thinking has already been started with generation {self.first_generation_id!r}')

        self.first_generation_id = generation.id
        self.generations[generation.id] = generation

    def add(self, connection: Connection, successor: Generation, *predecessors: Generation):
        for predecessor in predecessors:
            self.connections.setdefault(predecessor.id, {})[successor.id] = connection

    def retry(self, invalid: Generation, retry: Generation):
        self.add(Connection.RETRY, retry, invalid)

    def follow(self, consequence: Generation, *reasons: Generation):
        self.add(Connection.CONSEQUENCE, consequence, *reasons)

    def combine(self, combination: Generation, *facts: Generation):
        self.add(Connection.COMBINATION, combination, *facts)

    def conclude(self, conclusion: Generation, completion_index: int):
        assert conclusion.state == GenerationState.COMPLETED
        assert 0 <= completion_index < len(conclusion.completions)
        self.concluding_id = conclusion.id
        self.conclusion_index = completion_index

    def get_last_retry(self, generation: Generation) -> Generation:
        while generation.state == GenerationState.COMPLETED:

            connections = self.connections.get(generation.id)
            if connections is None:
                break

            for id, conn in connections.items():
                if conn == Connection.RETRY:
                    generation = self.generations[id]
                    break
            else:
                break

        return generation

    def get_by_label(self, label: str) -> Optional[Generation]:
        """Returns the latest completed generation with the specific label, also considering retries"""
        for generation in self.generations.values():
            if generation.label == label:
                return self.get_last_retry(generation)
        return None
