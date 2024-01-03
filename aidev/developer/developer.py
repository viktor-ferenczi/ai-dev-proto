import os.path
import random
from pprint import pprint
from typing import Iterable

from lxml import etree

from .mvc import Controller, Method, Coverage, View, Model
from ..common.util import load_text_file, iter_tree
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
            pprint(issue)
            if await brain.fix_issue(issue):
                self.project.stage_change('.')
                self.project.commit(f'{issue.key}: {issue.message}')
                self.project.analyze()
                query_open_issues()

        print('No more issues to fix.')

    async def create_test_fixture(self, branch_name: str):
        self.prepare_working_copy(branch_name)

        brain = Junior(self.project, self.engine)

        # For each controller with any uncovered request handler methods:
        ## Identify possible HTTP requests to cover with test fixtures, feed controllers+model+view
        ## Generate those fixtures one by one, give the HomeIndexTests as 1-shot example
        ## Build and run the test case
        ## Verify that the output of the fixture is reasonable
        ## Record the output as reference
        ## Run the test again, make sure it passes
        ## Commit the test
        # Repeat until all views are covered

        for controller in self.find_controllers():
            print(controller.model_dump_json(indent=2))

        print('All controller methods are covered with test fixtures.')

    def find_controllers(self) -> Iterable[Controller]:
        self.project.test_coverage()

        print('Finding controllers and their dependencies')
        coverage_path = os.path.join(self.project.project_dir, 'coverage.xml')
        coverage = load_text_file(coverage_path)
        tree = etree.fromstring(coverage)

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
                controller_source = load_text_file(path)

                methods: list[Method] = []
                for e_method in e_class.xpath('.//method'):

                    method_name = e_method.get('name')
                    if not method_name or not method_name[0].isalnum():
                        continue

                    view = View(name=f'{controller_name}/{method_name}', path=os.path.join(controller_view_dir, f'{method_name}.cshtml'))
                    view_source = load_text_file(view.path) if os.path.exists(view.path) else ''

                    # FIMXE: Sloppy text based match, use a code map!
                    models = [model for model in all_models if model.name in controller_source or model.name in view_source]

                    method = Method(
                        name=method_name,
                        view=view,
                        models=models,
                        coverage=Coverage.from_element(e_method)
                    )
                    methods.append(method)

                yield Controller(
                    name=controller_name,
                    path=path,
                    methods=methods,
                    coverage=Coverage.from_element(e_class)
                )
