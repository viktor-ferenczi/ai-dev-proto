"""Experiment to fix build errors

1. Start with a solution which can build just fine
2. Make a code map from the original code
3. Make a modification to the code intentionally introducing a non-trivial build error
4. Make a code map from the modified code
5. Build the solution and capture the error messages
6. Collect the known symbols from the error message
7. Collect the direct dependencies of those symbols
8. Collect the relevant parts of the source files which contain those symbols
9. Collect the corresponding parts of the original source files
10. Ask the LLM to fix the issue, include the relevant original and modified code
11. Re-integrate the modification into the modified code
12. Repeat from step 4. until the solution can build

Possible improvements:
- GoT by using multiple generations and going down multiple paths
- Scoring or comparing multiple fixes provided by the LLM to pick out the best

"""
import asyncio
from typing import Dict, Set

from aidev.code_map.model import CodeMap, Category, Symbol
from aidev.code_map.parsers import init_tree_sitter
from aidev.common.config import C
from aidev.common.util import render_workflow_template, extract_code_blocks
from aidev.editing.model import Document, Hunk, Block
from aidev.engine.params import GenerationParams, Constraint
from aidev.engine.vllm_engine import VllmEngine
from aidev.workflow.working_copy import WorkingCopy

SOLUTION_DIR = 'C:/Dev/AI/Coding/example-shop'


class State:

    def __init__(self, wc: WorkingCopy):
        self.paths: Set[str] = wc.list_versioned_paths()
        self.code_map: CodeMap = CodeMap.from_working_copy(wc, self.paths)


class Experiment:

    def __init__(self, solution_dir: str):
        self.wc = WorkingCopy(solution_dir, 'Shop')
        self.wc.rollback()
        self.wc.ensure_branch('exp_fix_build')
        self.states: Dict[str, State] = {}

    def capture_state(self, name: str):
        self.states[name] = State(self.wc)

    def get_paths(self, name: str) -> Set[str]:
        return self.states[name].paths

    def get_code_map(self, name: str) -> CodeMap:
        return self.states[name].code_map

    def change_code(self, relpath: str):
        assert relpath in self.states['original'].paths, f'File is not versioned: {relpath}'
        document = Document.from_file(self.wc.project_dir, relpath)
        document.lines[:] = [line for line in document.lines if not line.lstrip().startswith('using ') and not 'IEnumerable<Order> GetAll();' in line]
        document.write(self.wc.project_dir)

    def build(self):
        self.build_error = self.wc.build()

    def get_relevant_code(self, name: str, feedback: str):
        code_map = self.get_code_map(name)
        relevant_symbols = set(code_map.collect_symbols_from_text(feedback, {Category.TYPE, Category.FUNCTION, Category.VARIABLE}))
        dependency_symbols: Set[Symbol] = set(code_map.iter_dependency_symbols(relevant_symbols))
        relevant_symbols.update(dependency_symbols)
        return code_map.collect_relevant_sources(relevant_symbols)


async def main():
    engine = VllmEngine()

    e = Experiment(SOLUTION_DIR)

    relpath = 'Shop.Data/IOrder.cs'

    e.capture_state('original')
    e.change_code(relpath)
    e.capture_state('modified')

    e.build()
    assert e.build_error

    system = C.SYSTEM_CODING_ASSISTANT
    instruction = render_workflow_template(
        'feedback_build_error',
        error=e.build_error,
    )
    params = GenerationParams(n=1, temperature=0.3)
    completions = await engine.generate(system, instruction, params)
    feedback = completions[0]

    print('-' * 70)
    print('FEEDBACK:')
    print('-' * 70)
    print(feedback)
    print()

    original_source, original_hunks, original_symbol_ids = e.get_relevant_code('original', feedback)
    modified_source, modified_hunks, modified_symbol_ids = e.get_relevant_code('modified', feedback)

    oh = {h.document.path: h for h in original_hunks}
    mh = [h for h in modified_hunks if oh.get(h.document.path) and oh.get(h.document.path).document.code_block != h.document.code_block]

    task_description = '''\
Remove the `GetAll` method from the `IOrder` interface, because it is unused.

Path: `Shop.Data/IOrder.cs`

```cs
        IEnumerable<Order> GetAll();
```
'''

    implementation_plan = '''\
1. Verify that the GetAll method is not used anywhere else in the code.
2. Remove the `GetAll` method from the `IOrder` interface.
3. Remove all implementations of the `GetAll` method from all classes inheriting the `IOrder` interface.
'''

    system = C.SYSTEM_CODING_ASSISTANT

    instruction = render_workflow_template(
        'exp_fix_build',
        build_error=feedback,
        task_description=task_description,
        implementation_plan=implementation_plan,
        original_hunks=original_hunks,
        modified_hunks=mh,
    )

    print('-' * 70)
    print('SYSTEM:')
    print('-' * 70)
    print(system)
    print()

    print('-' * 70)
    print('INSTRUCTION:')
    print('-' * 70)
    print(instruction)
    print()

    pattern = rf'(Path: `(.*?)`\n\n`{{3}}([a-z]+)\n(\n|[^`].*?\n)*`{{3}}\n+)+'
    constraint = Constraint.from_regex(pattern)
    params = GenerationParams(n=1, temperature=0.5, constraint=constraint)
    completions = await engine.generate(system, instruction, params)

    for i, completion in enumerate(completions):
        print('-' * 70)
        print(f'COMPLETION {i}:')
        print('-' * 70)
        print(completion)
        print()

    for fixed_code in extract_code_blocks(completions[0]):
        break
    else:
        raise ValueError()

    fixed_document = Document.from_text(relpath, fixed_code)
    fixed_hunks = [Hunk.from_document(fixed_document, Block.from_range(0, fixed_document.line_count))]

    system = C.SYSTEM_CODING_ASSISTANT
    instruction = render_workflow_template(
        'exp_fix_build_reintegrate',
        implementation_plan=implementation_plan,
        original_hunks=[hunk for hunk in original_hunks if hunk.document.path == fixed_document.path],
        modified_hunks=fixed_hunks,
        code_block_type=fixed_document.code_block_type,
    )
    params = GenerationParams(n=1, temperature=0.3)
    completions = await engine.generate(system, instruction, params)
    for code in extract_code_blocks(completions[0]):
        print('-' * 70)
        print(f'REINTEGRATED:')
        print('-' * 70)
        print(code)
        print()


if __name__ == '__main__':
    init_tree_sitter()
    asyncio.run(main())
