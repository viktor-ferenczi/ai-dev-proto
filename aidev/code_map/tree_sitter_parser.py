from typing import Tuple, Dict

from tree_sitter import Parser, Tree

from .base_parser import BaseParser
from .model import Graph


class TreeSitterParser(BaseParser):
    is_code = True

    def __init__(self) -> None:
        super().__init__()
        self.unhandled: Dict[str, Tuple[int, str]] = {}

    def parse(self, graph: Graph, path: str, content: bytes):
        parser = Parser()
        parser.set_language(self.tree_sitter_language)
        tree: Tree = parser.parse(content)
        file_line_count = 1 + content.count(b'\n')
        self.collect(graph, path, tree, file_line_count)

    def collect(self, graph: Graph, path: str, tree: Tree, file_line_count: int):
        raise NotImplementedError()
