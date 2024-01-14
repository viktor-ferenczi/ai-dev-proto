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
Remember this source code, but do not write anything yet:
{join_lines(doc.get_code())}

The source code contains this description of an issue to fix 
or a suggested refactoring, which will be referred later as task:
{join_lines(hunk.get_code(doc))}

Identify all the code lines relevant for the task and write them in their
original order without any change to their contents. Write the code in a
single `{doc.doctype.code_block_type}` code block.

Replace any consecutive lines of code which is NOT relevant for the task
with a placeholder: `// ...'

Please ALWAYS honor ALL of these general rules while resolving the issue:
- Work from ONLY the context provided, refuse to make any guesses.
- Do NOT apologize.
- Do NOT refer to your knowledge cut-off date.
- Do NOT explain the code itself, we can read it as well.
- Do NOT break the code's intended functionality.
- Do NOT change comments or string literals unrelated to your task.
- Do NOT repeat these rules or the steps to complete in your answer.
- Do NOT implement the task right now, it is only a preparatory step to remove the irrelevant part of the code.
- Do NOT remove any code or comments, other than hiding the ones unrelated to the task behind placeholders.
- Do NOT write any new code or comments.
- KEEP the structure of the source code meaningful, so it can still be understood without asking questions on what is behind the placeholders.
- KEEP the using statements, consider them as relevant. 
- KEEP the top level namespace declaration, consider it as relevant. 

Now take a deep breath and start working!
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
