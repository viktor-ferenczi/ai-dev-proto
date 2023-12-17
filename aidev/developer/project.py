import os
from subprocess import check_output, Popen, STDOUT, PIPE


class Project:

    def __init__(self, project_dir: str):
        self.project_dir = project_dir

        self.aidev_dir = os.path.join(self.project_dir, ".aidev")
        self.attempts_dir = os.path.join(self.aidev_dir, "attempts")
        self.latest_path = os.path.join(self.aidev_dir, "latest.md")

        os.makedirs(self.aidev_dir, exist_ok=True)
        os.makedirs(self.attempts_dir, exist_ok=True)

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
        self.must_run_command('analyze project', ['analyze.bat'], shell=True)

    def get_current_branch(self) -> str:
        return check_output(["git", "branch", "--show-current"], cwd=self.project_dir).decode('utf-8').strip()

    def ensure_branch(self, name: str):
        if self.get_current_branch() != name:
            if self.checkout_branch(name):
                self.checkout_new_branch(name)

    def checkout_branch(self, name: str) -> str:
        return self.try_run_command('checkout branch', ["git", "checkout", name])

    def checkout_new_branch(self, name: str):
        self.must_run_command('create branch', ["git", "checkout", "-b", name])

    def checkout_head(self):
        self.must_run_command('checkout HEAD', ["git", "checkout", "HEAD"])

    def roll_back_changes(self, path: str):
        self.must_run_command('roll back changes', ["git", "checkout", path])

    def commit(self, message: str):
        self.must_run_command(f'commit staged changes', ["git", "commit", "-m", message])

    def stage_change(self, path: str):
        self.must_run_command('stage change', ["git", "add", path])

    def has_staged_changes(self) -> bool:
        _, output = self.run_command('check staged changes', ['git', 'status'])
        return 'nothing to commit, working tree clean' not in output

    def format_code(self):
        self.must_run_command(f'format code', ["dotnet", "format", '.'])

    def build(self) -> str:
        return self.try_run_command('build solution', ['dotnet', 'build'])

    def test(self) -> str:
        return self.try_run_command('test solution', ['dotnet', 'test', '--no-build', '--nologo', '--logger', 'console', '.'])
