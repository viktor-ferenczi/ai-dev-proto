from ..common.async_helpers import AsyncPool
from ..engine.engine import Engine
from .model import Solution


class GenerationOrchestrator:
    """Orchestrates LLMs to complete generations"""

    def __init__(self):
        super().__init__()
        self.engines: list[Engine] = []
        self.max_parallel_generations = 0

    def register_engine(self, engine: Engine):
        self.engines.append(engine)
        self.max_parallel_generations += engine.optimal_parallel_sequences

    async def run_until_complete(self, solution: Solution):
        async with AsyncPool() as pool:
            while solution.may_need_generation:
                self.start_generations(pool, solution)
                await pool.wait()

    def start_generations(self, pool: AsyncPool, solution: Solution):
        for generation in solution.iter_generations():
            for engine in self.engines:
                if generation.can_run_on(engine):
                    pool.run(generation.run_on(engine))
                    if pool.task_count >= self.max_parallel_generations:
                        return
                    break
