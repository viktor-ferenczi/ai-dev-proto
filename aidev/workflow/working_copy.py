import asyncio
import os
from subprocess import check_output, Popen, STDOUT, PIPE
from typing import Optional, Set

from ..common.config import C
from ..common.util import iter_tree


class WorkingCopy:

    def __init__(self, project_dir: str, project_name: str):
        self.project_dir: str = project_dir
        self.project_name: str = project_name

        self.config_path: str = os.path.join(self.project_dir, 'aidev.toml')
        self.aidev_dir: str = os.path.join(self.project_dir, ".aidev")
        self.tasks_dir: str = os.path.join(self.aidev_dir, "tasks")
        self.audit_dir: str = os.path.join(self.aidev_dir, "audit")
        self.latest_path: str = os.path.join(self.aidev_dir, "latest.md")

        self.tests_project_dir = os.path.join(project_dir, f'{project_name}.Tests')
        self.tests_project_path = os.path.join(self.tests_project_dir, f'{project_name}.Tests.csproj')

        self.sqlite_db_path = os.path.join(self.tests_project_dir, 'FoodShip.Test.db')

        os.makedirs(self.aidev_dir, exist_ok=True)
        os.makedirs(self.tasks_dir, exist_ok=True)
        os.makedirs(self.audit_dir, exist_ok=True)

        self.has_repository = os.path.isdir(os.path.join(self.project_dir, '.git'))

        self.lock: asyncio.Lock = asyncio.Lock()

    async def __aenter__(self):
        await self.lock.acquire()

        if self.has_changes():
            raise IOError(f'This working copy folder has unexpected changes: {self.project_dir}')

        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.roll_back_changes('.')
        self.lock.release()

    def load_config(self):
        if os.path.exists(self.config_path):
            C.load(self.config_path)

    def run_command(self, action: str, command: list[str], *, shell=False) -> (int, str):
        print(f'Command to {action}: {" ".join(command)}')
        process = Popen(command, cwd=self.project_dir, stdout=PIPE, stderr=STDOUT, shell=shell)
        output, _ = process.communicate()
        return process.returncode, output.decode('utf-8')

    def try_run_command(self, action: str, command: list[str], *, shell=False) -> str:
        exit_code, output = self.run_command(action, command, shell=shell)
        if exit_code:
            return f'Failed to {action}: {command!r}\nExit code: {exit_code}\nOutput:\n{output}'
        return ''

    def must_run_command(self, action: str, command: list[str], *, shell=False):
        error = self.try_run_command(action, command, shell=shell)
        if error:
            raise RuntimeError(error)

    def analyze(self):
        self.must_run_command('begin analyzing project using SonarScanner', ['dotnet', 'sonarscanner', 'begin', f'/k:{self.project_name}', f'/d:sonar.token={C.SONAR_TOKEN}'], shell=True)
        self.must_run_command('building the project with analysis enabled', ['dotnet', 'build'], shell=True)
        self.must_run_command('end analyzing project', ['dotnet', 'sonarscanner', 'end', f'/d:sonar.token={C.SONAR_TOKEN}'], shell=True)

    def get_current_branch(self) -> str:
        if not self.has_repository:
            return ''

        return check_output(["git", "branch", "--show-current"], cwd=self.project_dir).decode('utf-8').strip()

    def ensure_branch(self, name: str):
        if self.get_current_branch() != name:
            if self.checkout_branch(name):
                self.checkout_new_branch(name)

    def checkout_branch(self, name: str) -> str:
        if not self.has_repository:
            return ''

        return self.try_run_command('checkout branch', ["git", "checkout", name])

    def checkout_new_branch(self, name: str):
        if not self.has_repository:
            return

        self.must_run_command('create branch', ["git", "checkout", "-b", name])

    def checkout_head(self):
        if not self.has_repository:
            return

        self.must_run_command('checkout HEAD', ["git", "checkout", "HEAD"])

    def roll_back_changes(self, path: str):
        if not self.has_repository:
            return

        self.must_run_command('roll back changes', ["git", "checkout", path])

    def commit(self, message: str):
        if not self.has_repository:
            return

        self.must_run_command(f'commit staged changes', ["git", "commit", "-m", message])

    def stage_change(self, path: str):
        if not self.has_repository:
            return

        self.must_run_command('stage change', ["git", "add", path])

    def has_changes(self) -> bool:
        if not self.has_repository:
            return False

        _, output = self.run_command('check staged changes', ['git', 'status'])
        return 'nothing to commit, working tree clean' not in output

    def list_ignored_paths(self) -> Optional[Set[str]]:
        if not self.has_repository:
            return None

        returncode, output = self.run_command('list ignored files', ['git', 'ls-files', '--others', '--ignored', '--exclude-standard'])
        if returncode:
            return None

        # Returned paths are using slash (/) directory separators
        return {line.strip() for line in output.split('\n') if line.strip()}

    def format_code(self):
        self.must_run_command(f'format code', ["dotnet", "format", '.'])

    def clean(self):
        self.must_run_command('clean solution', ['dotnet', 'clean'])

    def build(self) -> str:
        return self.try_run_command('build solution', ['dotnet', 'build'])

    def test(self) -> str:
        return self.try_run_command('test solution', ['dotnet', 'test', '--no-build', '--nologo', '--logger', 'console', '.'])

    def test_coverage(self) -> str:
        coverage_path = os.path.join(self.project_dir, 'coverage.xml')
        if os.path.exists(coverage_path):
            os.remove(coverage_path)

        return self.try_run_command('collect test coverage', ['dotnet-coverage', 'collect', '-f', 'cobertura', '-o', 'coverage.xml', 'dotnet', 'test'])

    def find(self, filename: str) -> str:
        for path in iter_tree(self.project_dir):
            if path.endswith(f'{os.path.sep}{filename}'):
                return path
        return ''
