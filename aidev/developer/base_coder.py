from .project import Project
from ..engine.engine import Engine


class BaseCoder:

    def __init__(self, project: Project, engine: Engine):
        self.project = project
        self.engine = engine
