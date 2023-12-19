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

    def __init__(self):
        super().__init__(description='AI Developer CLI')

        # Common arguments
        self.add_argument('-v', '--verbose', action='count', default=0, help='Verbose logging')
        self.add_argument('-c', '--config', help='Path to the global configuration file [~/.aidev/config.toml]')
        self.add_argument('-p', '--project', default='.', help='Project directory [current directory]')
        self.add_argument('-n', '--name', default='Project', help='Name of the project [default: Project]')
        self.add_argument('-b', '--branch', default='ai-dev', help='Name of the Git branch to commit to [default: ai-dev]')

        # Subcommands
        self.subparsers = self.add_subparsers(dest='command', help='Subcommand')
        self.subparsers.required = True

        # Add 'fix' command
        fix = self.fix = self.subparsers.add_parser('fix', help='Fix issues')
        fix.add_argument('-s', '--source', default='sonar', help='Source of the issues to process [sonar]')

    # def format_help(self):
    #     common = super().format_help()
    #     fix = f'fix\n{self.fix.format_help()}'
    #     return f'{common}\n{fix}'


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
    if source != 'sonar':
        print(f'Unknown issue source: {source}', file=sys.stderr)
        sys.exit(1)

    sonar = SonarClient(project.project_name)
    engine = OpenAIEngine()
    developer = Developer(project, sonar, engine)
    asyncio.run(developer.fix_issues(branch))


COMMANDS = {
    'fix': command_fix,
}

if __name__ == '__main__':
    main()
