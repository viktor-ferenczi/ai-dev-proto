import asyncio
from asyncio import Future
from typing import Any, Callable, AsyncIterable, Coroutine, Set, Iterable


async def iter_async(iterable: Iterable[Any]) -> AsyncIterable[Any]:
    for v in iterable:
        yield v


async def map_async(func: Callable[[Any], Coroutine], iter_args: AsyncIterable[Any], max_tasks: int = 0) -> AsyncIterable[Any]:
    assert max_tasks > 0

    if max_tasks == 1:
        async for arg in iter_args:
            yield await func(arg)
        return

    pending: Set[Future] = set()
    try:
        async for arg in iter_args:
            pending.add(asyncio.create_task(func(arg)))
            if max_tasks > 0 and len(pending) >= max_tasks:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    yield task.result()
                del done
                del task

        if pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)
            for task in done:
                yield task.result()
    finally:
        for task in pending:
            task.cancel()


class AsyncPool:

    def __init__(self):
        self.pending: Set[Future] = set()

    @property
    def task_count(self) -> int:
        return len(self.pending)

    def run(self, coroutine: Coroutine):
        task = asyncio.create_task(coroutine)
        self.pending.add(task)

    async def join(self):
        try:
            while self.pending:
                await self.wait()
        finally:
            self.__cancel()

    async def wait(self):
        done, self.pending = await asyncio.wait(self.pending, return_when=asyncio.FIRST_COMPLETED)
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
