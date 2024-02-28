import unittest
from logging import DEBUG

from aidev.common.config import C
from aidev.common.util import set_slow_callback_duration_threshold, init_logger
from aidev.engine.engine import Engine
from aidev.engine.params import GenerationParams

LOG_REQUESTS = False


class EngineTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        set_slow_callback_duration_threshold(C.SLOW_CALLBACK_DURATION_THRESHOLD)
        logger = init_logger(DEBUG) if LOG_REQUESTS else None

        if C.ENGINE == 'openai':
            from aidev.engine.openai_engine import OpenAIEngine
            self.engine: Engine = OpenAIEngine(logger=logger)
        if C.ENGINE == 'vllm':
            from aidev.engine.vllm_engine import VllmEngine
            self.engine: Engine = VllmEngine(logger=logger)
        else:
            raise ValueError(f'Unknown engine: {C.ENGINE}')

        return await super().asyncSetUp()

    async def asyncTearDown(self):
        del self.engine
        return await super().asyncTearDown()

    async def test_add_using(self):
        system = "You are a helpful AI coding assistant. You give concise answers. If you do not know something, then say so."
        instruction = '''\
Add any missing using statements to the SOURCE-CODE below. 
Add using statements only to import standard .NET Core library namespaces as needed.

<SOURCE-CODE>

    public class OrderFilter
    {
        public string UserId { get; set; }
        public OrderBy OrderBy { get; set; }
        public int Offset { get; set; }
        public int Limit { get; set; }
        public decimal? MinimalPrice { get; set; }
        public decimal? MaximalPrice { get; set; }
        public DateTime? MinDate { get; set; }
        public DateTime? MaxDate { get; set; }
        public string ZipCode { get; set; }
    }
    
</SOURCE-CODE> 

'''
        params = GenerationParams(max_tokens=1000)
        completions = await self.engine.generate(system, instruction, params)

        for completion in completions:
            print(completion)
            self.assertTrue('using ' in completion)
