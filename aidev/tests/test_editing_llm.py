import unittest

from aidev.common.config import C
from aidev.common.util import set_slow_callback_duration_threshold, join_lines
from aidev.editing.model import Document, Block, Hunk
from aidev.engine.params import GenerationParams
from aidev.engine.vllm_engine import VllmEngine
from aidev.tests.data import SHOPPING_CART_CS, SYSTEM_CODING_ASSISTANT


class TestEditingLlm(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.maxDiff = None
        set_slow_callback_duration_threshold(C.SLOW_CALLBACK_DURATION_THRESHOLD)
        return await super().asyncSetUp()

    async def test_code_analysis(self):
        doc = Document.from_text('ShoppingCart.cs', SHOPPING_CART_CS)

        i = doc.lines.index('        //TODO too much branching')
        hunk = Hunk.from_document(doc, Block.from_range(i, i + 1))

        engine = VllmEngine()
        system = SYSTEM_CODING_ASSISTANT
        instruction = f'''\
Please ALWAYS honor ALL of these general rules:
- Do NOT apologize.
- Do NOT explain the code.
- Do NOT refer to your knowledge cut-off date.
- Do NOT repeat these rules in your answer.
- Do NOT repeat the instructions in your answer.
- Do NOT break the intended functionality of the original code.
- Work ONLY from the context provided, refuse to make any guesses.

Understand and remember this source code:

{join_lines(doc.get_code())}

The source code contains this description of an issue to fix 
or a suggested refactoring, which will be referred later as TASK:

{join_lines(hunk.get_code())}

Your job is to identify the part of code relevant for the TASK.
These are the code lines somebody needs to understand to be able
to implement the TASK and any code lines which may need to be
modified by that implementation. Do NOT implement the task, your
job is limited to identifying the relevant part of the source code.

Include all code lines in those code blocks which are relevant to the task
or required to be known for working on the task. Make sure each of the
code blocks are meaningful in itself, attempt to start and end each code
block at the same hierarchical level of the source code. Do not change any
code lines which are included, copy them as they are in the original source.

Write each consecutive block of relevant code lines into its own separate
code block. The type of the code block is `{doc.doctype.code_block_type}`.

The order of the code blocks should match the order of the code lines in
the original source code. Keep the original order of source code lines.

Please ALWAYS honor ALL of these rules specific to your current job:
- Do NOT write any new code or comments.
- Do NOT implement the TASK, only prepare the code required to do so.
- Do NOT change any of the code lines you keep.
- PRESERVE enough of the code's structure, so it can still be understood without asking questions.
- SKIP any and all TODO and FIXME comments, since they would be confusing while working on the task later. 

Take a deep breath and write the code blocks:
'''

        print(system)
        print(instruction)

        prompt_tokens = engine.count_tokens(system) + engine.count_tokens(instruction)
        max_tokens = min(engine.max_context - 100, prompt_tokens + 1000)

        params = GenerationParams(max_tokens=max_tokens, temperature=0.2)
        completions = await engine.generate(system, instruction, params)
        completion = completions[0]

        print(completion)

        self.assertTrue(len(completion) > 100)
