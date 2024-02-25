import argparse
import asyncio
import sys
import os
from logging import DEBUG
from typing import Optional, List

from aidev.code_map.parsers import init_tree_sitter
from aidev.common.config import C
from aidev.common.util import set_slow_callback_duration_threshold, join_lines, init_logger
from aidev.workflow.working_copy import WorkingCopy
from aidev.editing.model import Document
from aidev.engine.vllm_engine import VllmEngine
from aidev.sonar.client import SonarClient
from aidev.workflow.generation_orchestrator import GenerationOrchestrator
from aidev.workflow.model import Solution, Task
from aidev.workflow.task_orchestrator import TaskOrchestrator


class ArgParser(argparse.ArgumentParser):

    def __init__(self, add_subparsers=True, **kwargs):
        super().__init__(description='AI Developer CLI', **kwargs)
        self.subparsers = None

        if add_subparsers:
            # Common arguments
            self.add_argument('-v', '--verbose', action='count', default=0, help='Verbose logging')
            self.add_argument('-c', '--config', default='', help='Path to the global configuration file [~/.aidev/config.toml]')
            self.add_argument('-p', '--project', default='', help='Project directory [current directory]')
            self.add_argument('-n', '--name', default='', help='Name of the project [Project]')
            self.add_argument('-b', '--branch', default='', help='Name of the Git branch to commit to [aidev]')

            # Subcommands
            self.subparsers = self.add_subparsers(dest='command', help='Subcommand')
            self.subparsers.required = True

            fix_parser = self.subparsers.add_parser('fix', help='Fix issues', add_subparsers=False)
            fix_parser.add_argument('-s', '--source', default='sonar', choices=['sonar'], help='Source of the issues to process [sonar]')

            test_parser = self.subparsers.add_parser('test', help='Improve test coverage', add_subparsers=False)
            test_parser.add_argument('-k', '--keep', action='store_true', help='Keep code which compiles, but fails to test')
            # test_parser.add_argument('-u', '--unit', action='store_true', help='Create unit tests')
            # test_parser.add_argument('-f', '--fixture', action='store_true', help='Create test fixtures')

    def format_help(self):
        subcommand_helps = [super().format_help()]

        if self.subparsers:
            for name, subparser in self.subparsers.choices.items():
                subcommand_helps.append(f"{subparser.format_usage()[len('usage: '):].strip().replace('[-h] ', '', 1)}")
                subcommand_helps.append('  ' + subparser.format_help().partition('show this help message and exit\n')[2].strip())
                subcommand_helps.append('')

        return '\n'.join(subcommand_helps)


async def main(argv: Optional[List[str]] = None):
    if argv is None:
        argv = sys.argv[1:]

    parser = ArgParser()
    args = parser.parse_args(argv)

    command = args.command
    if not command:
        parser.print_help()
        return

    if command not in COMMANDS:
        print(f'Unknown command: {command}', file=sys.stderr)
        sys.exit(1)

    config_path = args.config
    if config_path:
        if not os.path.exists(config_path):
            raise IOError(f'Missing configuration file: {config_path}')
        C.load(config_path)

    project_dir = args.project or C.PROJECT_DIR or '.'

    project_config_path = os.path.join(project_dir, '.aidev', 'config.toml')
    if os.path.exists(project_config_path):
        C.load(project_config_path)

    project_name = args.name or C.PROJECT_NAME or 'Project'
    branch = args.branch or C.PROJECT_BRANCH or 'aidev'

    if not os.path.isdir(project_dir):
        print(f'The path "{project_dir}" is not a valid directory.', file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(os.path.join(project_dir, '.git')):
        print(f'The directory "{project_dir}" is not a Git working copy.', file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        C.VERBOSE = True

    assert project_name, 'Empty project name'
    assert branch, 'Empty branch name'

    print(f'Project directory: {project_dir}')
    print(f'Branch name: {branch}')

    set_slow_callback_duration_threshold(C.SLOW_CALLBACK_DURATION_THRESHOLD)

    project = WorkingCopy(project_dir, project_name)
    subparser = parser.subparsers.choices[command]
    subparser_argument_names = [action.dest for action in subparser._actions if action.__class__.__name__.startswith('_Store')]
    await COMMANDS[command](project, branch, **{name: getattr(args, name) for name in subparser_argument_names})


async def command_fix(project: WorkingCopy, branch: str, source: str):
    assert source == 'sonar', f'Unknown source: {source}'

    init_tree_sitter()

    solution = Solution.new(project.project_name, project.project_dir)
    print(f'Solution: {solution.name}')

    sonar = SonarClient(project.project_name)
    if not sonar.get_issues():
        print(f'Analyzing the project with SonarQube')
        project.analyze()

    print(f'Loading issues from SonarQube')
    for issue in sonar.get_issues():

        # FIXME: !!! Don't merge this !!!
        if issue.key != 'AY12XCHttlu1W1OPFn1y':
            continue

        if issue.textRange is None:
            description = issue.message
        else:
            document = Document.from_file(solution.folder, issue.sourceRelPath)
            code_block_type = document.doctype.code_block_type
            code_lines = document.lines[issue.textRange.startLine - 1:issue.textRange.endLine]
            description = (
                f'{issue.message}\n\n'
                f'This issue was reported for this source file: `{issue.sourceRelPath}`\n\n'
                f'Within that source file for these lines of code:\n\n'
                f'```{code_block_type}\n{join_lines(code_lines)}\n```\n'
            )

        task = Task(
            id=issue.key,
            ticket=issue.key,
            branch=branch,
            description=description,
        )

        solution.tasks[task.id] = task

    print(f'Picked up {len(solution.tasks)} issues')

    generation_orchestrator = GenerationOrchestrator(solution)

    logger = init_logger(loglevel=DEBUG) if C.VERBOSE else None
    engine = VllmEngine(logger=logger)
    generation_orchestrator.register_engine(engine)

    task_orchestrator = TaskOrchestrator(solution)

    print('Working...')
    await asyncio.wait([
        asyncio.create_task(generation_orchestrator.run_until_complete()),
        asyncio.create_task(task_orchestrator.run_until_complete()),
    ])

    print('Done')


async def command_test(project: WorkingCopy, branch: str, keep: bool):  # , unit: bool, fixture: bool
    raise NotImplementedError()


COMMANDS = {
    'fix': command_fix,
    'test': command_test,
}

if __name__ == '__main__':
    asyncio.run(main())
