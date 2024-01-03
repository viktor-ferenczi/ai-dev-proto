import os
import random
from typing import Iterable, Tuple

from .mvc import Controller, Method
from ..developer.junior import Junior
from ..developer.project import Project
from ..engine.engine import Engine
from ..sonar.client import SonarClient
from ..sonar.issue import Issue, IssueStatus


class Developer:

    def __init__(self, project: Project, sonar: SonarClient, engine: Engine):
        self.project = project
        self.sonar = sonar
        self.engine = engine

        self.rng = random.Random()

    def prepare_working_copy(self, branch_name):
        if self.project.has_changes():
            raise RuntimeError(f'Please make sure there are no changes in your working copy: {self.project.project_dir}')

        self.project.clean()

        self.project.ensure_branch(branch_name)

        self.project.format_code()
        self.project.stage_change('.')

        if self.project.has_changes():
            self.project.commit('Formatted code')

        error = self.project.build()
        if error:
            print(error)
            raise RuntimeError(f'Failed to build solution: {self.project.project_dir}')

    async def fix_issues(self, branch_name: str):
        self.prepare_working_copy(branch_name)

        issues: list[Issue] = []

        def query_open_issues():
            issues[:] = [i for i in self.sonar.get_issues() if i.status == IssueStatus.OPEN]

        self.project.analyze()
        query_open_issues()

        brain = Junior(self.project, self.engine)
        while issues:
            print(f'Choosing one from the {len(issues)} issues')
            issue = self.rng.choice(issues)
            if await brain.fix_issue(issue):
                self.project.stage_change('.')
                self.project.commit(f'{issue.key}: {issue.message}')
                self.project.analyze()
                query_open_issues()

        print('No more issues to fix.')

    async def create_test_fixtures(self, branch_name: str, max_attempts: int = 10):
        assert max_attempts > 0

        self.prepare_working_copy(branch_name)

        brain = Junior(self.project, self.engine)

        remaining = 0

        for attempt_index in range(max_attempts):
            temperature = 0.2 + (0.8 - 0.2) * attempt_index / max_attempts

            self.project.test_coverage()

            iter_controllers: Iterable[Controller] = (
                controller for controller in self.project.find_controllers()
            )

            def iter_methods() -> Iterable[Tuple[Controller, Method]]:
                for controller in iter_controllers:
                    for method in controller.methods:
                        yield (controller, method)

            controller_methods: list[Tuple[Controller, Method]] = [
                (controller, method)
                for controller, method in iter_methods()
                if method.coverage.branch_rate == 0
                   and not os.path.exists(method.test_path)
            ]

            if not controller_methods:
                break

            print(f'Methods remaining to cover: {len(controller_methods)}')

            self.rng.shuffle(controller_methods)

            remaining = 0
            for controller, method in controller_methods:
                print(f'Covering method: {controller.name}Controller.{method.name}')
                if await brain.cover_controller_method(controller, method, temperature=temperature, allow_failure=False):
                    print(f'Covered {controller.name}Controller.{method.name}')
                    self.project.stage_change('.')
                    self.project.commit(f'Covered {controller.name}Controller.{method.name}')
                else:
                    print(f'Failed to cover {controller.name}Controller.{method.name}')
                    remaining += 1

            if remaining:
                continue

        if remaining:
            print(f'Failed to cover {remaining} controller methods')
        else:
            print('Covered all controller methods')
