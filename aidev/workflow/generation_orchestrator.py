import asyncio

from ..common.async_helpers import AsyncPool
from ..engine.engine import Engine
from .model import Solution
from ..thinking.model import GenerationState


class GenerationOrchestrator:
    """Orchestrates LLMs to complete generations"""

    def __init__(self, solution: Solution):
        super().__init__()
        self.solution: Solution = solution
        self.engines: list[Engine] = []
        self.max_parallel_generations = 0

    def register_engine(self, engine: Engine):
        self.engines.append(engine)
        self.max_parallel_generations += engine.optimal_parallel_sequences

    async def run_until_complete(self):
        async with AsyncPool() as pool:
            while self.solution.has_any_tasks_remaining:
                self.start_new_generations(pool)
                if len(pool) >= self.max_parallel_generations:
                    await pool.wait()
                else:
                    # FIXME: Polling loop, should listen on the relevant changes instead
                    await asyncio.sleep(0.5)

    def start_new_generations(self, pool: AsyncPool):
        for generation in self.solution.iter_generations():

            if generation.state != GenerationState.PENDING:
                continue

            for engine in self.engines:
                if generation.can_run_on(engine):
                    generation.state = GenerationState.GENERATING
                    pool.run(generation.run_on(engine))
                    if len(pool) >= self.max_parallel_generations:
                        return
                    break
