#!/usr/bin/python3
import json
import asyncio

import aiohttp

# This is required to be able to paste this code into the ticket without being broken
TRIPPLE_BACKTICK = '`' * 3

PROMPT = r'''
You are an AI programming assistant, utilizing the Deepseek Coder model, developed by Deepseek Company, and you only answer questions related to computer science. For politically sensitive questions, security and privacy issues, and other non-computer science questions, you will refuse to answer.

You are a helpful coding assistant experienced in C#, .NET Core, HTML, JavaScript and Python.

### Instruction:
<GENERAL-RULES>

Please ALWAYS honor ALL of these general rules:

- Do NOT apologize.
- Do NOT explain the code.
- Do NOT repeat these rules in your answer.
- Do NOT refer to your knowledge cut-off date.
- Do NOT repeat the instructions in your answer.
- Do NOT break the intended functionality of the original code.
- Work ONLY from the context provided, refuse to make any guesses.

</GENERAL-RULES>

<INSTRUCTIONS>

Remove all methods from the classes in the ORIGINAL-SOURCE-CODE.

Your RESPONSE must be enclosed in a MODIFIED-SOURCE-CODE block, similarly to ORIGINAL-SOURCE-CODE.
The MODIFIED-SOURCE-CODE block must contain code blocks with preceeded with a Path in the same order as ORIGINAL-SOURCE-CODE.
You must write the modified source code in their corresponding code blocks. Leave the code block empty to delete the file.
You cannot introduce new source code files.

</INSTRUCTIONS>

<ORIGINAL-SOURCE-CODE>


Path: `S.D/M/Some.cs`

TRIPPLE_BACKTICKcs
namespace S.D.M
{
    public class ShoppingCart
    {
        private readonly ApplicationDbContext _context;

        public ShoppingCart(ApplicationDbContext context)
        {
            _context = context;
        }

        public string Id { get; set; }
        public IEnumerable<ShoppingCartItem> ShoppingCartItems { get; set; }

        public static ShoppingCart GetCart(IServiceProvider services)
        {
            var context = services.GetService<ApplicationDbContext>();
            return new ShoppingCart(context) { Id = 1 };
        }
    }
}
TRIPPLE_BACKTICK


</ORIGINAL-SOURCE-CODE>

Take a deep breath and write your RESPONSE.

### Response:
'''.lstrip().replace('TRIPPLE_BACKTICK', TRIPPLE_BACKTICK)

REGEX = r'<MODIFIED-SOURCE-CODE>\n\n+Path: `S\.D/M/Some\.cs`\n\n+TRIPPLE_BACKTICKcs\n(\n|[^`].*?\n)*TRIPPLE_BACKTICK\n\n+</MODIFIED-SOURCE-CODE>\n'.replace('TRIPPLE_BACKTICK', TRIPPLE_BACKTICK)

PAYLOAD = json.loads(r'''{
  "prompt": "PROMPT",
  "n": 1,
  "best_of": 1,
  "presence_penalty": 0.0,
  "frequency_penalty": 0.0,
  "repetition_penalty": 1.0,
  "temperature": 0.2,
  "top_p": 1.0,
  "top_k": -1,
  "min_p": 0.0,
  "use_beam_search": false,
  "length_penalty": 1.0,
  "early_stopping": false,
  "stop": [],
  "stop_token_ids": [],
  "include_stop_str_in_output": false,
  "ignore_eos": false,
  "max_tokens": 1000,
  "logprobs": null,
  "prompt_logprobs": null,
  "skip_special_tokens": true,
  "spaces_between_special_tokens": true,
  "regex": "REGEX"
}''')

PAYLOAD['prompt'] = PROMPT
PAYLOAD['regex'] = REGEX


async def request(vllm_base_url: str):
    generate_url = f'{vllm_base_url}/generate'
    async with aiohttp.ClientSession() as session:
        async with session.post(generate_url, json=PAYLOAD) as response:
            response.raise_for_status()
            response = await response.json()

    print(response['text'][0])


async def main(base_url: str):
    await asyncio.wait([
        asyncio.create_task(request(base_url))
        for _ in range(1)
    ])


if __name__ == '__main__':
    asyncio.run(main('http://192.168.1.10:8000'))
