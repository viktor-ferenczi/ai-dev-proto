import unittest

from aidev.common.config import C
from aidev.common.util import set_slow_callback_duration_threshold
from aidev.editing.model import Document
from aidev.engine.openai_engine import OpenAIEngine
from aidev.engine.params import GenerationParams
from aidev.tests.data import SHOPPING_CART_CS, SYSTEM_CODING_ASSISTANT


class TestEditingLlm(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.maxDiff = None
        set_slow_callback_duration_threshold(C.SLOW_CALLBACK_DURATION_THRESHOLD)
        self.document = Document.from_text('ShoppingCart.cs', SHOPPING_CART_CS)
        return await super().asyncSetUp()

    async def test_code_analysis(self):
        hunk = self.document.edit()
        code_block = hunk.get_code_block_for_editing(self.document)

        engine = OpenAIEngine()
        system = SYSTEM_CODING_ASSISTANT
        instruction = '''\
Analyze the code below and make a few very concise suggestions on how to improve it.
{code_block}
'''.format(code_block='\n'.join(code_block))

        print(system)
        print(instruction)

        params = GenerationParams(max_tokens=1000)
        completions = await engine.generate(system, instruction, params)
        completion = completions[0]

        print(completion)

        self.assertTrue(len(completion) > 100)
