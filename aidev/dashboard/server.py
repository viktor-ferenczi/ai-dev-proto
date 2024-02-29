import asyncio
from typing import Optional

import quart
from aiodebug import log_slow_callbacks
from quart import Response, render_template

from ..common.async_helpers import run_app
from ..common.config import C
from ..workflow.model import Solution

app = quart.Quart(__name__, template_folder=C.HTML_TEMPLATES_DIR)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config["DEBUG"] = True

# app = quart_cors.cors(app, allow_origin="https://chat.openai.com")


SOLUTION: Optional[Solution] = None


@app.get("/canary")
async def index():
    await asyncio.sleep(0)
    return 'OK', 200


@app.get("/")
async def get_solution():
    if SOLUTION is None:
        return Response(response='No current solution', status=404)

    response = await render_template("solution.html", solution=SOLUTION)
    return Response(response=response, status=200)


@app.get("/task/<task_id>")
async def get_task(task_id: str):
    if SOLUTION is None:
        return Response(response='No current solution', status=404)

    task = SOLUTION.tasks.get(task_id)
    if task is None:
        return Response(response='No such task', status=404)

    response = await render_template("task.html", task=task)
    return Response(response=response, status=200)


@app.get("/test/")
async def get_test():
    response = await render_template("test.html", code='```cs\nclass Class<T> {}\n```')
    return Response(response=response, status=200)


async def main():
    await run_app(app, debug=C.VERBOSE, host="localhost", port=8000)


if __name__ == "__main__":
    log_slow_callbacks.enable(0.1)
    asyncio.run(main())
