import random
from pprint import pprint
from typing import List, Optional

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

        self.issues: Optional[List[Issue]] = None
        self.issue: Optional[Issue] = None
        self.issue_index: int = 0

        self.rng = random.Random()

    async def fix_issues(self, branch_name: str):
        if self.project.has_changes():
            raise RuntimeError(f'Please make sure there are no changes in your working copy: {self.project.project_dir}')

        self.project.ensure_branch(branch_name)

        self.project.format_code()
        self.project.stage_change('.')
        if self.project.has_changes():
            self.project.commit('Formatted code')

        self.project.analyze()
        self.query_open_issues()

        brain = Junior(self.project, self.engine)
        while self.issues:
            print(f'Choosing one from the {len(self.issues)} issues')
            self.issue = self.rng.choice(self.issues)
            pprint(self.issue)
            if await brain.fix_issue(self.issue):
                self.project.stage_change('.')
                self.project.commit(f'{self.issue.key}: {self.issue.message}')
                self.project.analyze()
                self.query_open_issues()

        print('No more issues to fix.')

    def query_open_issues(self):
        self.issues = [issue for issue in self.sonar.get_issues() if issue.status == IssueStatus.OPEN]

    async def create_test_fixture(self, branch_name: str):
        pass
