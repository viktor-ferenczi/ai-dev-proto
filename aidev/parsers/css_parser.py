import uuid
from typing import Iterator, Set, List

from tree_sitter import Parser, Tree, TreeCursor, Node

from ..common.config import C
from ..common.util import decode_normalize
from ..common.util import tiktoken_len, new_uuid
from common.tree import walk_children
from model.fragment import Fragment
from parsers.base_parser import BaseParser
from ..splitters.text_splitter import TextSplitter


class CssParser(BaseParser):
    name = 'CSS'
    extensions = ('css',)
    mime_types = ('text/css',)
    tree_sitter_language_name = 'css'
    is_code = True

    def __init__(self) -> None:
        super().__init__()
        self.splitter = TextSplitter(
            chunk_size=C.MAX_TOKENS_PER_FRAGMENT,
            length_function=tiktoken_len,
            separators=(
                ('<', r"^.*?{"),
            )
        )

    def parse(self, path: str, content: bytes) -> Iterator[Fragment]:
        parser = Parser()
        parser.set_language(self.tree_sitter_language)
        tree: Tree = parser.parse(content)
        cursor: TreeCursor = tree.walk()

        classes: List[str] = []
        class_set: Set[str] = set()

        debug = False
        for child, depth in walk_children(cursor):
            node: Node = child.node
            if debug and not node.child_count:
                print(f"@{depth}|{node.type}|{decode_normalize(node.text)}|")
            lineno = 1 + node.start_point[0]
            if node.type == 'class_name':
                name = decode_normalize(node.text)
                if name not in class_set:
                    classes.append(name)
                    class_set.add(name)
                for sentence in self.splitter.split_text(decode_normalize(node.parent.text)):
                    yield Fragment(new_uuid(), path, lineno + sentence.lineno - 1, depth, 'class', name, sentence.text, tiktoken_len(sentence.text))

        summary = []
        if classes:
            summary.append("  Classes: {' '.join(classes)}")

        summary = ''.join(f'{line}\n' for line in summary)
        yield Fragment(new_uuid(), path, 1, 0, 'summary', '', summary, tiktoken_len(summary))
