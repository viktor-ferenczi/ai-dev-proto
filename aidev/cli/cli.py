import argparse
import asyncio
import sys
import os
from typing import Optional

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
            self.add_argument('-c', '--config', help='Path to the global configuration file [~/.aidev/config.toml]')
            self.add_argument('-p', '--project', default='.', help='Project directory [current directory]')
            self.add_argument('-n', '--name', default='Project', help='Name of the project [default: Project]')
            self.add_argument('-b', '--branch', default='ai-dev', help='Name of the Git branch to commit to [default: ai-dev]')

            # Subcommands
            self.subparsers = self.add_subparsers(dest='command', help='Subcommand')
            self.subparsers.required = True

            fix_parser = self.subparsers.add_parser('fix', help='Fix issues', add_subparsers=False)
            fix_parser.add_argument('-s', '--source', default='sonar', choices=['sonar'], help='Source of the issues to process [sonar]')

            test_parser = self.subparsers.add_parser('test', help='Improve test coverage', add_subparsers=False)
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


def main(argv: Optional[list[str]] = None):
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

    project_dir = args.project
    project_name = args.name
    branch = args.branch

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

    project = Project(project_dir, project_name)
    subparser = parser.subparsers.choices[command]
    subparser_argument_names = [action.dest for action in subparser._actions if isinstance(action, argparse._StoreAction)]
    COMMANDS[command](project, branch, **{name: getattr(args, name) for name in subparser_argument_names})


def command_fix(project: Project, branch: str, source: str):
    assert source == 'sonar', source
    sonar = SonarClient(project.project_name)
    engine = OpenAIEngine()
    developer = Developer(project, sonar, engine)
    asyncio.run(developer.fix_issues(branch))


def command_test(project: Project, branch: str):  # , unit: bool, fixture: bool
    engine = OpenAIEngine()
    # FIXME: Refactor the code to allow for working without sonar
    developer = Developer(project, None, engine)
    asyncio.run(developer.create_test_fixtures(branch))


COMMANDS = {
    'fix': command_fix,
    'test': command_test,
}

if __name__ == '__main__':
    main()
