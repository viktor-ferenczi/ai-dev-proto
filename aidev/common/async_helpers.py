from asyncio import Future, Semaphore, create_task, as_completed, Event, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from typing import Set, Iterable, AsyncIterable, Callable, Coroutine

import quart


async def iter_async[T](iterable: Iterable[T]) -> AsyncIterable[T]:
    for v in iterable:
        yield v


async def map_async_worker[R](semaphore: Semaphore, coro: Coroutine[None, None, R]) -> R:
    async with semaphore:
        return await coro


async def map_async[T, R](async_func: Callable[[T], Coroutine[None, None, R]], concurrency: int, async_iter_args: AsyncIterable[T]) -> AsyncIterable[R]:
    if concurrency > 1:
        semaphore = Semaphore(concurrency)
        workers = [create_task(map_async_worker(semaphore, async_func(arg))) async for arg in async_iter_args]
        for completed_worker in as_completed(workers):
            yield await completed_worker
    elif concurrency == 1:
        async for arg in async_iter_args:
            yield await async_func(arg)
    else:
        raise ValueError(f'Invalid concurrency (must be a positive integer): {concurrency!r}')


class AsyncPool:

    def __init__(self):
        self.pending: Set[Future] = set()
        self.__added = Event()

    def __len__(self) -> int:
        return len(self.pending)

    def __nonzero__(self) -> bool:
        return bool(self.pending)

    def run(self, coroutine: Coroutine):
        task = create_task(coroutine)
        self.pending.add(task)
        self.__added.set()
        self.__added.clear()

    async def join(self):
        try:
            while self.pending:
                await self.wait()
        finally:
            self.__cancel()

    async def wait(self):
        if not self.pending:
            return

        done, self.pending = await wait(self.pending, return_when=FIRST_COMPLETED)
        for task in done:
            task.result()

    def __cancel(self):
        for task in self.pending:
            task.cancel()

        self.pending.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            await self.join()
        else:
            self.__cancel()


async def run_app(app: quart.Quart, *coros: Coroutine, **kws):
    print(f'{datetime.now(timezone.utc).isoformat()}: Service started')

    tasks = [create_task(coro) for coro in coros]

    await app.run_task(**kws)

    for task in tasks:
        task.cancel()
