from .project import Project
from ..engine.engine import Engine
from ..sonar.issue import Issue


class Brain:

    def __init__(self, project: Project, engine: Engine):
        self.project = project
        self.engine = engine

    async def fix_issue(self, issue: Issue) -> bool:
        raise NotImplementedError()
