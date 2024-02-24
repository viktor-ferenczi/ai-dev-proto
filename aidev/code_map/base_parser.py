from typing import Tuple

import tree_sitter
from .model import Graph
from ..common.config import C


class BaseParser:
    name: str = ''
    extensions: Tuple[str] = ()
    mime_types: Tuple[str] = ()
    tree_sitter_language_name: str = ''
    tree_sitter_subdir: Tuple[str] = ()
    tree_sitter_language: tree_sitter.Language  # Set automatically
    is_code = False
    debug = C.VERBOSE

    def __init__(self) -> None:
        assert self.name
        assert self.extensions
        assert self.mime_types

    def parse(self, graph: Graph, path: str, content: bytes):
        raise NotImplementedError()
