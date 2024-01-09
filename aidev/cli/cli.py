import argparse
import asyncio
import sys
import os
from typing import Optional

from aidev.common.config import C
from aidev.common.util import set_slow_callback_duration_threshold
from aidev.developer.developer import Developer
from aidev.developer.project import Project
from aidev.engine.openai_engine import OpenAIEngine
from aidev.sonar.client import SonarClient


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


async def main(argv: Optional[list[str]] = None):
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

    assert project_name, 'Empty project name'
    assert branch, 'Empty branch name'

    print(f'Project directory: {project_dir}')
    print(f'Branch name: {branch}')

    set_slow_callback_duration_threshold(C.SLOW_CALLBACK_DURATION_THRESHOLD)

    project = Project(project_dir, project_name)
    subparser = parser.subparsers.choices[command]
    subparser_argument_names = [action.dest for action in subparser._actions if action.__class__.__name__.startswith('_Store')]
    await COMMANDS[command](project, branch, **{name: getattr(args, name) for name in subparser_argument_names})


async def command_fix(project: Project, branch: str, source: str):
    assert source == 'sonar', source
    sonar = SonarClient(project.project_name)
    engine = OpenAIEngine()
    developer = Developer(project, sonar, engine)
    await developer.fix_issues(branch)


async def command_test(project: Project, branch: str, keep: bool):  # , unit: bool, fixture: bool
    engine = OpenAIEngine()
    # FIXME: Refactor the code to allow for working without sonar
    developer = Developer(project, None, engine)
    await developer.create_test_fixtures(branch, keep)


COMMANDS = {
    'fix': command_fix,
    'test': command_test,
}

if __name__ == '__main__':
    asyncio.run(main())
