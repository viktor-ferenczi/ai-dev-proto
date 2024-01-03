import os.path
import shutil
from typing import Dict

from .mvc import Controller, Method
from ..common.config import C
from ..common.util import get_next_free_numbered_file, read_text_file, read_text_files, write_text_file, read_text_file_or_default
from ..engine.params import GenerationParams
from ..sonar.issue import Issue, TextRange
from .attempt import Attempt, AttemptState
from .brain import Brain

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

INSTRUCTION_BUG_FIX = '''\
Consider the following original source code from an ASP.NET service based on .NET Core:
```{doctype}
{top_marker}
{source}
```

The static code analysis found an issue in the original source code:
```
{issue_description}
```

The issue is reported at these code lines:
```{doctype}
{code_lines}
```

- Issue category: {issue_category}
- Issue severity: {issue_severity}


Please ALWAYS honor ALL of these general rules while resolving the issue:
- Work ONLY from the context provided, refuse to make any guesses.
- Do NOT write any code if you do not have enough information in this context
  to resolve the issue or you do not know how to fix it.
- Do NOT use any kind of placeholders, always write out the full code.
- Do NOT lose any of the original (intended) functionality, remove only the bug. 
- Do NOT apologize.
- Do NOT refer to your knowledge cut-off date.
- Do NOT explain the code itself, we can read it as well.
- Do NOT include excessive comments.
- Do NOT remove original comments unrelated to the issue or the code modified.
- Do NOT break the code's intended functionality.
- Do NOT introduce any performance or security issues.
- Do NOT change comments or string literals unrelated to your task.
- Do NOT remove code (even if it is commented out or disabled) unless asked explicitly.
- Do NOT repeat these rules or the steps below in your answer.
- Do UPDATE comments which apply to code you have to change.
- ALWAYS write code which is easily readable by humans.
- Process the whole original source code, starting from and including the TOP_MARKER.
- If you are asked to remove code, then DO REMOVE it, not just comment it out.
- If you are asked to remove commented out code, then DO REMOVE it. Do NOT uncomment it.


Make sure the understand all the above, then work on resolving the issue by completing these steps:

1. Take a deep breath and think about the problem. Provide a very concise,
   step by step plan for resolving the issue. It will serve only for your 
   reference and not part of the actual output.

2. Stop here and ignore the rest of tasks if and only if you feel that
   some crucial information is missing to properly solve the issue or
   you do not know how to solve it. 

3. Copy the WHOLE original source code with modifications to resolve the issue.
   Your modifications should be concise and limited to the topic of the
   issue. Do NOT modify any code, data or comments unrelated to the issue.
   Do NOT attempt to fix or cleanup anything which is unrelated to the issue.
   Make sure that your changes are compatible with all existing functionality.
   Provide the modified source code in a SINGLE CODE BLOCK without the use of
   any placeholders. Write out the full code, because it will replace the original.

4. Check these failure conditions by reviewing the changes your made to the source code.
   - Are the changes you made fail to fully resolve the issue?
   - Have you missed any related changes humans would expect to be part as your issue resolution? 
   - Have you made any changes, additions or removals to code, data or comments not related to the issue?
   - Has any part of the source code replaced by a placeholder?
   
   If the answer to all of these questions are NO, then approve the code changes
   by saying "APPROVE_CHANGES" and nothing else after the code block.
   If you do not approve the changes, then provide a concise explanation why.'''

INSTRUCTION_TEST_FIXTURE_CODE = '''\
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


Valid database IDs to use in the request parameters by table name:
```
{formatted_db_ids}
```


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

Write only the source code for the test fixture in a code block and nothing else.
If you are unsure or miss some details in the context, then do not write anything.'''

EXAMPLE_HOME_INDEX_TEST = '''\
using Microsoft.Extensions.Tools.Internal;
using Shop.Tests.Tools;
using System.Net;
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
            Assert.True(response.IsSuccessStatusCode);
        }

        [Fact]
        public async Task Get_Content()
        {
            _webApp.Logout();

            var response = await _webApp.Client.GetAsync("/");
            var content = await response.Content.ReadAsStringAsync();
            Assert.True(response.IsSuccessStatusCode);

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
            Assert.True(response.IsSuccessStatusCode);

            var normalizedContent = Normalization.NormalizePageContent(content);

            var reference = new Reference("HomeIndexAuthenticated.html");
            reference.Verify(normalizedContent);
        }
    }
}'''


def extract_replacement_from_completion(original: str, completion: str, top_marker: str, rng: TextRange) -> (str, str):
    i = completion.find('```')
    j = completion.rfind('```')

    if i < 0 or j <= i:
        return 'Missing code block', ''

    i = completion.find('\n', i) + 1
    if i <= 0:
        return 'Missing newline after start of code block', ''

    replacement = completion[i:j].lstrip()

    if not replacement.strip():
        return 'Empty replacement', replacement

    if not replacement.startswith(top_marker):
        return 'Replacement is missing the TOP_MARKER', replacement

    replacement = replacement[len(top_marker) + 1:]

    if not replacement.strip():
        return 'Empty replacement after TOP_MARKER', replacement

    if replacement == original:
        return 'No change', replacement

    original = original.rstrip('\n') + '\n'
    replacement = replacement.rstrip('\n') + '\n'

    original_lines = original.splitlines(keepends=True)
    replacement_lines = replacement.splitlines(keepends=True)

    if len(original_lines) == len(replacement_lines) and all((a.rstrip() == b.rstrip()) for a, b in zip(original_lines, replacement_lines)):
        return 'Only whitespace changes after stripping trailing whitespace', replacement

    if '```' in replacement:
        return 'Multiple code blocks (ambiguous)', replacement

    if 'APPROVE_CHANGES' not in completion[:i] and 'APPROVE_CHANGES' not in completion[j:]:
        return 'Changes not approved by self-review', replacement

    return '', replacement


def extract_code_from_completion(completion: str) -> (str, str):
    i = completion.find('```')
    j = completion.rfind('```')

    if i < 0 or j <= i:
        return 'Missing code block', ''

    i = completion.find('\n', i) + 1
    if i <= 0:
        return 'Missing newline after start of code block', ''

    code = completion[i:j].lstrip()
    if not code.strip():
        return 'Empty code', ''

    return '', code


class Junior(Brain):

    async def fix_issue(self, issue: Issue) -> bool:
        print(f'Working on issue: {issue.key}')

        # FIXME: Can work only on a single source file at a time
        path = os.path.normpath(os.path.join(self.project.project_dir, issue.sourceRelPath))
        if not os.path.exists(path):
            print(f'Cannot find source file: {path}')
            return False

        # FIXME: Hardcoded source file encoding (utf-8-sig is to remove the BOM)
        # FIXME: Can work only on a single source file at a time
        with open(path, 'rt', encoding='utf-8-sig') as f:
            original = f.read()

        rng = issue.textRange
        if rng is None:
            print(f'ERROR: No text range in issue: {issue.key}')
            return False

        system = SYSTEM
        extension = path.rsplit('.')[-1].lower()
        top_marker = C.TOP_MARKER_BY_EXTENSION.get(extension)
        instruction = INSTRUCTION_BUG_FIX.format(
            source=original,
            doctype=C.DOCTYPE_BY_EXTENSION.get(extension, ''),
            top_marker=top_marker,
            issue_description=issue.message,
            issue_category=f'{issue.cleanCodeAttribute} ({issue.cleanCodeAttributeCategory})',
            issue_severity=issue.severity,
            code_lines='\n'.join(original.split('\n')[rng.startLine - 1:rng.endLine])
        )

        system_token_count = self.engine.count_tokens(system)
        instruction_token_count = self.engine.count_tokens(instruction)
        input_token_count = system_token_count + instruction_token_count
        remaining_tokens = self.engine.max_context - input_token_count - 2000
        max_tokens_to_generate = min(remaining_tokens, 2000 + instruction_token_count * 2)
        params = GenerationParams(
            number_of_completions=16,
            max_tokens=max_tokens_to_generate,
            temperature=0.3,
        )

        completions = await self.engine.generate(system, instruction, params)
        assert len(completions) == params.number_of_completions

        def new_attempt(completion: str) -> Attempt:
            error_, replacement = extract_replacement_from_completion(original, completion, top_marker, rng)
            state = AttemptState.INVALID if error_ else AttemptState.GENERATED

            attempt_ = Attempt(
                state=state,
                error=error_,
                path=path,
                issue=issue,
                original=original,
                system=system,
                instruction=instruction,
                params=params,
                completion=completion,
                replacement=replacement,
            )

            if attempt_.state == AttemptState.GENERATED and attempt_.count_modified_lines() < 1:
                attempt_.state = AttemptState.INVALID
                attempt_.error = 'No lines changed'

            return attempt_

        attempts = [new_attempt(completion) for completion in completions]
        attempts.sort(key=lambda attempt_: attempt_.count_modified_lines())

        issue_log_dir = os.path.join(self.project.attempts_dir, f'{issue.key}')
        os.makedirs(issue_log_dir, exist_ok=True)
        index = get_next_free_numbered_file(issue_log_dir)
        for offset, attempt in enumerate(attempts):
            attempt.log_path = os.path.join(issue_log_dir, f'{index + offset:04d}.md')
            # attempt.write_log()

        for attempt in attempts:
            if attempt.state != AttemptState.GENERATED:
                continue

            # FIXME: Related changes in other files: Provide the model with the original and modified code. Then each of the other source files separately. Ask it to check whether the other source needs to be updated to be compatible with the change.
            # FIXME: Optimize by checking only the files which may possibly be relevant, use a code map (namespace references, symbol usages) to narrow down what needs to be checked.
            if self.apply_code_change(attempt):
                error = self.project.build()
                if error:
                    attempt.state = AttemptState.BUILD_FAILED
                    attempt.error = error
                else:
                    error = self.project.test()
                    if error:
                        attempt.state = AttemptState.TEST_FAILED
                        attempt.error = error
                    else:
                        attempt.state = AttemptState.COMPLETED
            else:
                attempt.state = AttemptState.INVALID
                attempt.error = 'No code change after formatting the code'

            attempt.write_log()

            if attempt.state == AttemptState.COMPLETED:
                print(f'Completed issue: {issue.key}')
                return True

            self.project.roll_back_changes(attempt.path)

        print(f'Failed to solve issue: {issue.key}')
        return False

    def apply_code_change(self, attempt) -> bool:
        write_text_file(attempt.path, attempt.replacement)
        self.project.format_code()
        modified_source = read_text_file(attempt.path)
        return modified_source.rstrip() != attempt.original.rstrip()

    def revert_code_change(self, attempt):
        write_text_file(attempt.path, attempt.original)

    async def cover_controller_method(self, controller: Controller, method: Method, db_ids: Dict[str, list[int]], *, allow_failure=False, temperature: float = 0.3):
        print(f'Adding test fixture for {controller.name}Controller.{method.name}')

        if not os.path.isdir(self.project.tests_project_dir):
            raise IOError(f'Missing Tests project: {self.project.tests_project_dir}')

        controller_source = read_text_file(controller.path)
        model_sources = [model.path for model in method.models]

        formatted_db_ids = '\n'.join(f'{table_name}: {ids!r}' for table_name, ids in db_ids.items())

        system = SYSTEM
        instruction = INSTRUCTION_TEST_FIXTURE_CODE.format(
            controller=controller,
            method=method,
            example_source=EXAMPLE_HOME_INDEX_TEST.replace('Shop.', f'{self.project.project_name}.'),
            controller_source=controller_source,
            models_source='\n\n'.join(read_text_files(model_sources)),
            formatted_db_ids=formatted_db_ids,
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
            error_, code = extract_code_from_completion(completion)
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
