import os
import re
from subprocess import check_output, Popen, STDOUT, PIPE
from typing import Iterable
from lxml import etree

from .mvc import Controller, Model, Method, Coverage, View
from ..common.config import C
from ..common.util import read_text_file, iter_tree, remove_lines, keep_lines, read_binary_file


class Project:

    def __init__(self, project_dir: str, project_name: str):
        self.project_dir: str = project_dir
        self.project_name: str = project_name

        self.config_path: str = os.path.join(self.project_dir, 'aidev.toml')
        self.aidev_dir: str = os.path.join(self.project_dir, ".aidev")
        self.attempts_dir: str = os.path.join(self.aidev_dir, "attempts")
        self.latest_path: str = os.path.join(self.aidev_dir, "latest.md")

        self.tests_project_dir = os.path.join(project_dir, f'{project_name}.Tests')
        self.tests_project_path = os.path.join(self.tests_project_dir, f'{project_name}.Tests.csproj')

        os.makedirs(self.aidev_dir, exist_ok=True)
        os.makedirs(self.attempts_dir, exist_ok=True)

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

    def has_changes(self) -> bool:
        _, output = self.run_command('check staged changes', ['git', 'status'])
        return 'nothing to commit, working tree clean' not in output

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

    def find_controllers(self) -> Iterable[Controller]:
        print('Finding controllers and their dependencies')
        coverage_path = os.path.join(self.project_dir, 'coverage.xml')
        tree = etree.fromstring(read_binary_file(coverage_path))

        web_server_dir = ''
        all_models: list[Model] = []

        for e_package in tree.xpath('.//package'):
            for e_class in e_package.xpath('.//class'):

                class_name = e_class.get('name')
                if not class_name or not class_name[0].isalnum():
                    continue
                if not class_name.endswith('Controller'):
                    continue

                controller_name = class_name.rsplit('.')[-1][:-len('Controller')]
                path = e_class.get('filename')

                if not web_server_dir:

                    web_server_dir = path
                    while web_server_dir:
                        web_server_dir, suffix = os.path.split(web_server_dir)
                        if suffix == 'Controllers':
                            break
                    assert web_server_dir, f'No Controllers parent folder found for controller class: {os.path.split(path)}'

                    models_dir = os.path.join(web_server_dir, 'Models')
                    for model_path in iter_tree(models_dir):
                        if model_path.endswith('Model.cs'):
                            _, model_filename = os.path.split(model_path)
                            model_name = model_filename[:-len('.cs')]
                            all_models.append(Model(name=model_name, path=model_path))

                controller_view_dir = os.path.join(web_server_dir, 'Views', controller_name)
                controller_source = read_text_file(path)
                controller_source = remove_lines(controller_source, re.compile(r'^using\s.*;\s*$'))

                methods: list[Method] = []
                for e_method in e_class.xpath('.//method'):

                    method_name = e_method.get('name')
                    if not method_name or not method_name[0].isalnum():
                        continue

                    # FIXME: Use a code map instead to verify whether this method is a request handler (return value or attributes)
                    pattern = rf'(public|protected|private)\s+IActionResult\s+{method_name}\s*\(.*?\)\s*$'
                    async_pattern = rf'(public|protected|private)\s+async\s+Task<IActionResult>\s+{method_name}\s*\(.*?\)\s*$'
                    if (not re.search(pattern, controller_source, re.DOTALL | re.MULTILINE) and not re.search(async_pattern, controller_source, re.DOTALL | re.MULTILINE)):
                        continue

                    method_signature = e_method.get('signature')

                    view = View(name=f'{controller_name}/{method_name}', path=os.path.join(controller_view_dir, f'{method_name}.cshtml'))
                    view_source = read_text_file(view.path) if os.path.exists(view.path) else ''
                    view_source = keep_lines(view_source, re.compile(r'^@model\s.*'))

                    # FIMXE: Sloppy text based match, use a code map!
                    models = [model for model in all_models if model.name in controller_source or model.name in view_source]

                    method = Method(
                        name=method_name,
                        signature=method_signature,
                        view=view,
                        models=models,
                        coverage=Coverage.from_element(e_method),
                        test_path=os.path.join(self.tests_project_dir, 'Fixtures', f'{controller_name}{method_name}Tests.cs'),
                        output_path=os.path.join(self.tests_project_dir, 'Output', 'Actual', f'{controller_name}{method_name}.html'),
                        reference_path=os.path.join(self.tests_project_dir, 'Output', 'Reference', f'{controller_name}{method_name}.html'),
                    )
                    methods.append(method)

                yield Controller(
                    name=controller_name,
                    path=path,
                    methods=methods,
                    coverage=Coverage.from_element(e_class),
                )

    def is_covered(self, controller: Controller, method: Method) -> bool:
        coverage_path = os.path.join(self.project_dir, 'coverage.xml')
        tree = etree.fromstring(read_binary_file(coverage_path))

        for e_package in tree.xpath('.//package'):
            for e_class in e_package.xpath('.//class'):

                class_name = e_class.get('name')
                if not class_name or not class_name[0].isalnum():
                    continue
                if not class_name.endswith('Controller'):
                    continue

                controller_name = class_name.rsplit('.')[-1][:-len('Controller')]
                if controller_name != controller.name:
                    continue

                for e_method in e_class.xpath('.//method'):
                    method_name = e_method.get('name')
                    method_signature = e_method.get('signature')
                    if method_name == method.name and method_signature == method.signature:
                        coverage = Coverage.from_element(e_method)
                        return coverage.branch_rate == 1.0

        raise ValueError(f'Cannot find method in coverage data: {controller.name}Controller.{method.name}')
