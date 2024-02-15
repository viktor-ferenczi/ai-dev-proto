import os
from pprint import pformat

from pydantic import BaseModel
from tree_sitter import Tree, TreeCursor

from .tree_sitter_util import walk_nodes, find_first_node
from .model import Graph, Symbol, Category, Relation, Block
from .tree_sitter_parser import TreeSitterParser
from ..common.util import decode_normalize


class Context(BaseModel):
    parent: Symbol
    relation: Relation
    last_lineno: int
    depth: int

    @classmethod
    def new(cls, parent: Symbol, relation: Relation, last_lineno: int, depth: int) -> 'Context':
        return cls(parent=parent, relation=relation, last_lineno=last_lineno, depth=depth)


class CshtmlParser(TreeSitterParser):
    name = 'Cshtml'
    extensions = ('cshtml',)
    mime_types = ('text/x-cshtml',)
    tree_sitter_language_name = 'html'

    def collect(self, graph: Graph, path: str, tree: Tree, file_line_count: int):
        source_basename = os.path.basename(path)
        source_name = os.path.splitext(source_basename)[0]
        source = Symbol.new(path, Category.SOURCE, Block.from_range(0, file_line_count), source_name)
        graph.add_symbol(source)

        ctx: Context = Context.new(source, Relation.PARENT, file_line_count - 1, -1)
        if self.debug:
            print(f'CTX: {pformat(ctx)}')
        stack: list[Context] = []

        def push(c: Context):
            nonlocal ctx
            assert c.last_lineno <= ctx.last_lineno, f'Invalid context blocks: {c.last_lineno} > {ctx.last_lineno}'
            stack.append(ctx)
            ctx = c
            if self.debug:
                print(f'CTX: {"> " * len(stack)}{pformat(ctx)}')

        cursor: TreeCursor = tree.walk()
        for node, lineno, depth in walk_nodes(cursor, debug=self.debug):
            last_lineno = lineno + node.text.count(b'\n')
            block = Block.from_range(lineno, last_lineno + 1)

            while depth <= ctx.depth:
                ctx = stack.pop()
                if self.debug:
                    print(f'CTX: {"> " * len(stack)}{pformat(ctx)}')

            if node.type == 'text' and ctx.parent.category == Category.SOURCE:
                text = decode_normalize(node.text)
                if text.startswith('@model '):
                    name = text.split(' ', 1)[1].strip()
                    symbol = Symbol.new(path, Category.USING, block, name)
                    graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                    continue

            start_tag = find_first_node(node, 'element', 'start_tag')
            if start_tag is not None:
                tag_name = find_first_node(start_tag, 'start_tag', 'tag_name')
                assert tag_name is not None
                name = decode_normalize(tag_name.text)
                symbol = Symbol.new(path, Category.ELEMENT, block, name)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                push(Context.new(symbol, Relation.CHILD, last_lineno, depth))
                continue

            attribute_name = find_first_node(node, 'attribute', 'attribute_name')
            if attribute_name is not None:
                qval = find_first_node(node, 'attribute', 'quoted_attribute_value')
                if qval is not None:
                    name = decode_normalize(attribute_name.text)
                    attribute = Symbol.new(path, Category.ATTRIBUTE, block, name)
                    graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, attribute)
                    if name.lower() == 'asp-controller':
                        attribute_value = find_first_node(qval, 'quoted_attribute_value', 'attribute_value')
                        value = decode_normalize(attribute_value.text)
                        controller = Symbol.new(path, Category.CONTROLLER, block, value)
                        graph.add_symbol_and_relation_both_ways(attribute, ctx.relation, controller)
                    elif name.lower() == 'asp-action':
                        attribute_value = find_first_node(qval, 'quoted_attribute_value', 'attribute_value')
                        value = decode_normalize(attribute_value.text)
                        controller = Symbol.new(path, Category.ACTION, block, value)
                        graph.add_symbol_and_relation_both_ways(attribute, ctx.relation, controller)
                continue

    def cross_reference(self, graph: Graph, path: str):
        for symbol in graph.symbols.values():
            if symbol.path != path:
                continue

            if symbol.category == Category.USING:
                for namespace_def in graph.symbols.values():
                    if namespace_def.category == Category.NAMESPACE and namespace_def.name == symbol.name:
                        graph.add_relation_both_ways(symbol, Relation.USES, namespace_def)

            if symbol.category == Category.CONTROLLER:
                class_name = f'{symbol.name}Controller'
                for other in graph.symbols.values():
                    if other.category == Category.CLASS and other.name == class_name:
                        graph.add_relation_both_ways(symbol, Relation.USES, other)

            # FIXME: Make is stricter by checking that the class is referred as a controller
            if symbol.category == Category.ACTION:
                for other in graph.symbols.values():
                    if other.category == Category.FUNCTION and other.name == symbol.name:
                        graph.add_relation_both_ways(symbol, Relation.USES, other)
