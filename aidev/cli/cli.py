import argparse
import asyncio
import subprocess
import sys
import os

from aidev.developer.developer import Developer
from aidev.developer.project import Project
from aidev.engine.openai_engine import OpenAIEngine
from aidev.sonar.client import SonarClient


def create_argument_parser():
    parser = argparse.ArgumentParser(
        description='AI Developer CLI',
        epilog='''\
The CLI works only on SonarQube issues, currently.
It is planned to have a command like "fix-sonar" in the future. 
''')

    parser.add_argument('-p', '--project', default='.', help='Project directory [default: current directory]')
    parser.add_argument('-n', '--name', default='Shop', help='SonarQube project name [default: Shop]')
    parser.add_argument('-b', '--branch', default='ai-dev', help='Name of the branch to work in [default: ai-dev]')

    return parser


def main():
    parser = create_argument_parser()
    args = parser.parse_args()

    project_dir = args.project
    project_name = args.name
    branch_name = args.branch

    if not os.path.isdir(project_dir):
        print(f'The path "{project_dir}" is not a valid directory.', file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(os.path.join(project_dir, '.git')):
        print(f'The directory "{project_dir}" is not a Git working copy.', file=sys.stderr)
        sys.exit(1)

    assert project_name, 'Empty project name'
    assert branch_name, 'Empty branch name'

    print(f'Project directory: {project_dir}')
    print(f'Branch name: {branch_name}')

    project = Project(project_dir)
    sonar = SonarClient(project_name)
    engine = OpenAIEngine()
    developer = Developer(project, sonar, engine)
    asyncio.run(developer.fix_issues(branch_name))


if __name__ == '__main__':
    main()
