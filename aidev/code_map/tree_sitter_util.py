from typing import Iterator, Tuple, Union, Iterable, Optional

from tree_sitter import TreeCursor, Node

from ..common.config import C
from ..common.util import decode_normalize, count_lines


def walk_children(cursor: TreeCursor, depth=0, *, max_depth=30) -> Iterator[TreeCursor]:
    if depth > max_depth:
        return

    node: Node = cursor.node
    child_count = node.child_count
    if not child_count:
        return

    cursor.goto_first_child()
    for i in range(child_count):
        if i:
            cursor.goto_next_sibling()
        yield cursor, depth
        yield from walk_children(cursor, depth + 1)

    cursor.goto_parent()


def walk_nodes(cursor: TreeCursor, *, max_depth: int = 30, debug: bool = False, log_multiline: bool = False) -> Iterator[Tuple[Node, int, int]]:
    for cur, depth in walk_children(cursor, max_depth=max_depth):
        node: Node = cur.node
        lineno = node.start_point[0]
        if debug and node.type.strip():
            text = decode_normalize(node.text).rstrip()
            if '\n' in text and not log_multiline:
                text = text.split('\n', 1)[0] + f'... {1 + count_lines(text)} lines'
            print(f"|#{lineno:05d} {'  ' * depth}[{node.type}] {text}")
        yield node, lineno, depth


class N:

    def __init__(self, typ: str, *alts: 'N'):
        self.typ = typ
        self.alts: Tuple[N, ...] = alts


def match_nodes(cursor: TreeCursor, nesting: N, *, max_depth: int = 30, debug: bool = False, log_multiline=False) -> Iterator[Node]:
    for node, lineno, depth in walk_nodes(cursor, max_depth=max_depth, debug=debug, log_multiline=log_multiline):
        yield from match_nest(node, nesting)


def match_nest(node: Node, nesting: N) -> Iterable[Node]:
    for child in node.children:
        if child.type != nesting.typ:
            continue
        if nesting.alts:
            for alt in nesting.alts:
                yield from match_nest(child, alt)
        else:
            yield child


def find_first_node(parent: Node, parent_type, *types: str) -> Optional[Node]:
    if parent.type != parent_type:
        return None

    node = parent
    for part in types:
        for child in node.children:
            if child.type == part:
                node = child
                break
        else:
            return None
    return node


def find_first_nodes(parent: Node, *type_lists: Iterable[str]) -> Optional[list[Node]]:
    assert type_lists
    nodes = [find_first_node(parent, *typs) for typs in type_lists]
    if any(node is None for node in nodes):
        return None
    return nodes


def find_all_nodes(node: Node, *types: str) -> Iterable[Node]:
    if node.type != types[0]:
        return

    tail = types[1:]
    if not tail:
        yield node
        return

    for child in node.children:
        yield from find_all_nodes(child, *tail)
