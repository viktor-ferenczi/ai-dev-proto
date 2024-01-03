import random
from pprint import pprint

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
        await self.prepare_working_copy(branch_name)

        self.project.analyze()

        brain = Junior(self.project, self.engine)

        # Run test coverage analysis
        # Identify the views not covered yet
        # For each uncovered view:
        ## Identify possible HTTP requests to cover with test fixtures, feed controllers+model+view
        ## Generate those fixtures one by one, give the HomeIndexTests as 1-shot example
        ## Build and run the test case
        ## Verify that the output of the fixture is reasonable
        ## Record the output as reference
        ## Run the test again, make sure it passes
        ## Commit the test
        # Repeat until all views are covered

        while 1:
            break

        print('All views are covered with test fixtures.')
