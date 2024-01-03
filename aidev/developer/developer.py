import os
import random

from .mvc import Controller
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
        self.project.ensure_branch(branch_name)
        self.project.format_code()
        self.project.stage_change('.')
        if self.project.has_changes():
            self.project.commit('Formatted code')

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

    async def create_test_fixtures(self, branch_name: str):
        self.prepare_working_copy(branch_name)

        brain = Junior(self.project, self.engine)

        controllers: list[Controller] = []

        def find_controllers_with_uncovered_methods():
            controllers[:] = [
                controller
                for controller in self.project.find_controllers()
                if controller.methods
                   and any(method.coverage.branch_rate < 1.0 for method in controller.methods)
            ]

        self.project.test_coverage()
        find_controllers_with_uncovered_methods()

        while controllers:
            print(f'Choosing one from the {len(controllers)} remaining controllers')
            controller: Controller = self.rng.choice(controllers)

            # FIXME: Partially covered methods are considered as covered. Improve existing test coverage separately.
            uncovered_methods = [method for method in controller.methods if method.coverage.branch_rate == 0.0]
            if not uncovered_methods:
                print('No uncovered methods to choose from, skipping controller')
                continue
            print(f'Choosing one from the {len(uncovered_methods)} uncovered methods')
            method = self.rng.choice(uncovered_methods)

            if os.path.exists(method.test_path):
                print(f'WARN: Class {controller.name}{method.name}Tests already exists: {method.test_path}')
                continue

            print(f'Covering method: {controller.name}Controller.{method.name}')
            if await brain.cover_controller_method(controller, method):
                print(f'Covered {controller.name}Controller.{method.name}')
                self.project.stage_change('.')
                self.project.commit(f'Covered {controller.name}Controller.{method.name}')
                find_controllers_with_uncovered_methods()
            else:
                print(f'Failed to cover {controller.name}Controller.{method.name}')

        print('All controller methods have been covered')
