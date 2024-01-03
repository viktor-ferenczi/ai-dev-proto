from pydantic import BaseModel
from lxml import etree


class Coverage(BaseModel):
    line_rate: float = 0.0
    branch_rate: float = 0.0
    complexity: float = 0.0

    @classmethod
    def from_element(cls, element: etree._Element) -> 'Coverage':
        return cls(
            line_rate=float(element.get('line-rate')),
            branch_rate=float(element.get('branch-rate')),
            complexity=float(element.get('complexity')),
        )


class Model(BaseModel):
    name: str
    path: str


class View(BaseModel):
    name: str
    path: str


class Method(BaseModel):
    name: str
    view: View
    models: list[Model]
    coverage: Coverage


class Controller(BaseModel):
    name: str
    path: str
    methods: list[Method]
    coverage: Coverage
