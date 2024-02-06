from typing import Iterator, Tuple

from tree_sitter import Node

from ..common.config import C
from ..common.util import tiktoken_len
from .model import Code
from .tree_sitter_parser import TreeSitterParser
from ..splitters.text_splitter import TextSplitter


class CSharpParser(TreeSitterParser):
    name = 'CSharp'
    extensions = ('cs',)
    mime_types = ('text/x-csharp',)
    tree_sitter_language_name = 'c_sharp'

    categories = {
        'namespace': 'Namespaces',
        'interface': 'Interfaces',
        'class': 'Classes',
        'method': 'Methods',
        'variable': 'Variables',
        'usage': 'Usages'
    }

    def __init__(self) -> None:
        super().__init__()
        self.splitter = TextSplitter(
            chunk_size=C.MAX_TOKENS_PER_FRAGMENT,
            length_function=tiktoken_len,
            separators=(
                ('<', r"^\s+namespace\s+"),
                ('<', r"^\s+interface\s+"),
                ('<', r"^\s+class\s+"),
                ('<', r"^\s+using\s+"),
                ('<', r"^\s+while\s+"),
                ('<', r"^\s+for\s+"),
                ('<', r"^\s+if\s+"),
                ('<', r"^\s+elif\s+"),
                ('<', r"^\s+else\s+"),
                ('<', r"^\s+try\s+"),
            )
        )

    def collect_names(self, nodes: Iterator[Tuple[Node, int, int]]):
        for node, lineno, depth in nodes:
            # namespace
            if node.type == "namespace_declaration":
                for child in node.children:
                    if child.type == "identifier":
                        yield Code(category="namespace", name=child.text, definition=node.text, lineno=lineno, depth=depth)

            # interface
            elif node.type == "interface_declaration":
                for child in node.children:
                    if child.type == "identifier":
                        yield Code(category="interface", name=child.text, definition=node.text, lineno=lineno, depth=depth)

            # class
            elif node.type == "class_declaration":
                for child in node.children:
                    if child.type == "identifier":
                        yield Code(category="class", name=child.text, definition=node.text, lineno=lineno, depth=depth)

            # method
            elif node.type in ("method_declaration", "constructor_declaration"):
                for child in node.children:
                    if child.type == "identifier":
                        yield Code(category="method", name=child.text, definition=node.text, lineno=lineno, depth=depth)

            # variable (definition)
            elif node.type == "variable_declaration":
                for child in node.children:
                    if child.type == "identifier":
                        yield Code(category="variable", name=child.text, definition=node.text, lineno=lineno, depth=depth)

            # variable (usage)
            elif node.type == "identifier":
                if node.parent and node.parent.type not in ("variable_declaration", "method_declaration",
                                                            "constructor_declaration", "class_declaration",
                                                            "interface_declaration", "namespace_declaration"):
                    yield Code(category="variable", name=node.text, definition='', lineno=lineno, depth=depth)
