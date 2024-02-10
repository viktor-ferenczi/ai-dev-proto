from ..workflow.working_copy import WorkingCopy
from ..engine.engine import Engine


class BaseCoder:

    def __init__(self, project: WorkingCopy, engine: Engine):
        self.project = project
        self.engine = engine
