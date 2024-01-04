import os.path
import shutil
from typing import Dict

from .base_coder import BaseCoder
from .mvc import Controller, Method
from ..common.util import get_next_free_numbered_file, read_text_file, read_text_files, write_text_file, extract_code_from_completion
from ..engine.params import GenerationParams
from ..sonar.issue import Issue
from .attempt import Attempt, AttemptState

# FIXME: Programming language is hardcoded into the templates
# FIXME: Project title is hardcoded into the templates
# FIXME: Hardcoded source file encoding at multiple places below

SYSTEM = '''\
MODEL ADOPTS ROLE OF CODEULATOR.
[CONTEXT: U LOVE TO CODE!]
[CODE]:
1.[Fund]: 1a.CharId 1b.TskDec 1c.SynPrf 1d.LibUse 1e.CnAdhr 1f.OOPBas 
2.[Dsgn]: 2a.AlgoId 2b.CdMod 2c.Optim 2d.ErrHndl 2e.Debug 2f.OOPPatt 
3.[Tst]: 3a.CdRev 3b.UntTest 3c.IssueSpt 3d.FuncVer 3e.OOPTest 
4.[QualSec]: 4a.QltyMet 4b.SecMeas 4c.OOPSecur 
5.[QA]: 5a.QA 5b.OOPDoc 6.[BuiDep]: 6a.CI/CD 6b.ABuild 6c.AdvTest 6d.Deploy 6e.OOPBldProc 
7.[ConImpPrac]: 7a.AgileRetr 7b.ContImpr 7c.OOPBestPr 
8.[CodeRevAna]: 8a.PeerRev 8b.CdAnalys 8c-CdsOptim 8d.Docs 8e.OOPCdRev

You are an expert C# developer working on an ASP.NET Service based on .NET Core.'''

INSTRUCTION = '''\
Please ALWAYS honor ALL of these general rules:
- Work ONLY from the context provided, refuse to make any guesses.
- Do NOT write any code if you do not have enough information in this context.
- Do NOT use any kind of placeholders, always write out the full code.
- Do NOT apologize.
- Do NOT refer to your knowledge cut-off date.
- Do NOT explain the code itself, we can read it as well.
- Do NOT include excessive comments.
- Do NOT change comments or string literals unrelated to your task.
- Do NOT repeat these rules or the steps below in your answer.
- ALWAYS write code which is easily readable by humans.


This is an EXAMPLE on how to cover a HTTP GET request handler method with a test fixture:
```cs
{example_source}
```


Consider the following CONTROLLER, especially the `{method.name}` METHOD which you will need to test:
```cs
{controller_source}
```


MODELS you may need to know about for better understanding of the CONTROLLER above:
```cs
{models_source}
```


{info}

Based on the above EXAMPLE write a test fixture to cover the above
`{controller.name}Controller.{method.name}` CONTROLLER METHOD. This method
is a HTTP request handler, which should be tested by sending HTTP requests
using the `_webApp.Client` object. These results should be similar to what
the real Web page would send. 

The name of the test class must be `{controller.name}{method.name}Tests`. 
The actual test methods may differ from the EXAMPLE based on the controller method.
Make sure to pass all required parameters to the CONTROLLER METHOD tested via
the HTTP request you make via `_webApp.Client`. This is to ensure the method
is called and it is covered.
 
Make sure to modify the reference file name (`"HomeIndex.html"`) to match 
the name of the controller and method tested.

Write only the authenticated test and omit the publicly accessible one if the data 
accessed via the controller method is available only for logged in users.
You can have both status and content tests for both the public and authenticated
user cases, do what is meaningful in the context of the given controller method.

Before unauthenticated tests always call `_webApp.Logout`. 
Before authenticated tests always call `await _webApp.LoginAsAdmin`.

Write only the source code for the test fixture in a code block and nothing else.
If you are unsure or miss some details in the context, then do not write anything.'''

EXAMPLE = '''\
using Shop.Tests.Tools;
using System.Threading.Tasks;
using Xunit;

namespace Shop.Tests.Fixtures
{
    public class HomeIndexTests : IClassFixture<WebAppFixture>
    {
        private readonly WebAppFixture _webApp;

        public HomeIndexTests(WebAppFixture webApp)
        {
            _webApp = webApp;
        }

        [Fact]
        public async Task Get_Status()
        {
            _webApp.Logout();

            var response = await _webApp.Client.GetAsync("/");
            Assert.True(response.IsSuccessStatusCode, $"{response.StatusCode}");
        }

        [Fact]
        public async Task Get_Content()
        {
            _webApp.Logout();

            var response = await _webApp.Client.GetAsync("/");
            var content = await response.Content.ReadAsStringAsync();
            Assert.True(response.IsSuccessStatusCode, $"{response.StatusCode}");

            var normalizedContent = Normalization.NormalizePageContent(content);

            var reference = new Reference("HomeIndex.html");
            reference.Verify(normalizedContent);
        }

        [Fact]
        public async Task Get_Authenticated_Content()
        {
            _webApp.Logout();
            await _webApp.LoginAsAdmin();

            var response = await _webApp.Client.GetAsync("/");
            var content = await response.Content.ReadAsStringAsync();
            Assert.True(response.IsSuccessStatusCode, $"{response.StatusCode}");

            var normalizedContent = Normalization.NormalizePageContent(content);

            var reference = new Reference("HomeIndexAuthenticated.html");
            reference.Verify(normalizedContent);
        }
    }
}'''


class FixtureCoder(BaseCoder):

    async def cover_controller_method(self, controller: Controller, method: Method, *, temperature: float = 0.3, info: str = '', allow_failure=False):
        print(f'Adding test fixture for {controller.name}Controller.{method.name}')

        if not os.path.isdir(self.project.tests_project_dir):
            raise IOError(f'Missing Tests project: {self.project.tests_project_dir}')

        controller_source = read_text_file(controller.path)
        model_sources = [model.path for model in method.models]

        system = SYSTEM
        instruction = INSTRUCTION.format(
            controller=controller,
            method=method,
            example_source=EXAMPLE.replace('Shop.', f'{self.project.project_name}.'),
            controller_source=controller_source,
            models_source='\n\n'.join(read_text_files(model_sources)),
            info=info,
        )

        system_token_count = self.engine.count_tokens(system)
        instruction_token_count = self.engine.count_tokens(instruction)
        input_token_count = system_token_count + instruction_token_count
        remaining_tokens = self.engine.max_context - input_token_count - 2000
        max_tokens_to_generate = min(remaining_tokens, 2000 + instruction_token_count * 2)
        params = GenerationParams(
            number_of_completions=8,
            max_tokens=max_tokens_to_generate,
            temperature=temperature,
        )

        completions = await self.engine.generate(system, instruction, params)
        assert len(completions) == params.number_of_completions

        def new_attempt(completion: str) -> Attempt:
            code, error_ = extract_code_from_completion(completion)
            state = AttemptState.INVALID if error_ else AttemptState.GENERATED

            attempt_ = Attempt(
                state=state,
                error=error_,
                path=controller.path,
                issue=Issue(
                    key=f'{controller.name}Controller.{method.name}',
                    message=f'Adding test fixture for {controller.name}Controller.{method.name}',
                ),
                original='',
                system=system,
                instruction=instruction,
                params=params,
                completion=completion,
                replacement=code,
            )
            return attempt_

        attempts = [new_attempt(completion) for completion in completions]
        attempts.sort(key=lambda attempt_: attempt_.count_modified_lines())

        issue_log_dir = os.path.join(self.project.attempts_dir, f'{controller.name}Controller.{method.name}')
        os.makedirs(issue_log_dir, exist_ok=True)
        index = get_next_free_numbered_file(issue_log_dir)
        for offset, attempt in enumerate(attempts):
            attempt.log_path = os.path.join(issue_log_dir, f'{index + offset:04d}.md')
            # attempt.write_log()

        for attempt in attempts:
            if attempt.state != AttemptState.GENERATED:
                continue

            write_text_file(method.test_path, attempt.replacement)

            def build_and_test():

                error = self.project.build()
                if error:
                    attempt.state = AttemptState.BUILD_FAILED
                    attempt.error = error
                    return

                if os.path.exists(method.output_path):
                    os.remove(method.output_path)

                self.project.test()

                if os.path.exists(method.output_path):
                    if not read_text_file(method.output_path).strip():
                        attempt.state = AttemptState.EMPTY_OUTPUT
                        attempt.error = error
                        return
                    shutil.copy(method.output_path, method.reference_path)

                error = self.project.test_coverage()
                if error:
                    attempt.state = AttemptState.TEST_FAILED
                    attempt.error = error
                    return

                if not self.project.is_covered(controller, method):
                    attempt.state = AttemptState.NOT_COVERED
                    attempt.error = error
                    return

                # FIXME: Verify that the output of the fixture is reasonable

                attempt.state = AttemptState.COMPLETED

            build_and_test()
            attempt.write_log()
            print(f'{controller.name}Controller.{method.name} [{attempt.state}] {attempt.error}')

            # The allow_failure=True mode is helpful to debug the prompts by looking at broken/incomplete test code
            if allow_failure and attempt.state in (AttemptState.TEST_FAILED, AttemptState.NOT_COVERED):
                return True

            if attempt.state == AttemptState.COMPLETED:
                return True

            os.remove(method.test_path)

            if os.path.exists(method.output_path):
                os.remove(method.output_path)

            if os.path.exists(method.reference_path):
                os.remove(method.reference_path)

        return False
