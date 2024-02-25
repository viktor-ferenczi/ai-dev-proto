from pprint import pformat
from typing import List

from pydantic import BaseModel
from tree_sitter import Tree, TreeCursor

from .tree_sitter_util import walk_nodes, find_first_node
from .model import Graph, Symbol, Category, Block, Reference, NAMESPACE_AWARE_CATEGORIES
from .tree_sitter_parser import TreeSitterParser
from ..common.util import decode_normalize


class Context(BaseModel):
    parent: Symbol
    depth: int

    @classmethod
    def new(cls, parent: Symbol, depth: int) -> 'Context':
        return cls(parent=parent, depth=depth)


class CSharpParser(TreeSitterParser):
    name = 'CSharp'
    extensions = ('cs',)
    mime_types = ('text/x-csharp',)
    tree_sitter_language_name = 'c_sharp'

    def collect(self, graph: Graph, path: str, tree: Tree, file_line_count: int):
        source = graph.new_source(path, file_line_count)

        ctx: Context = Context.new(source, -1)
        if self.debug:
            print(f'CTX: {pformat(ctx)}')
        stack: List[Context] = []

        def push(c: Context):
            nonlocal ctx
            assert c.depth > ctx.depth, f'Invalid context blocks: {c.depth} <= {ctx.depth}'
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

            identifier = find_first_node(node, 'using_directive', 'qualified_name')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                graph.new_symbol(ctx.parent, Category.USING, name, block)
                ctx.parent.references.add(Reference.new(name, Category.NAMESPACE))
                continue

            identifier = find_first_node(node, 'namespace_declaration', 'qualified_name')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = graph.new_symbol(ctx.parent, Category.NAMESPACE, name, block)
                push(Context.new(symbol, depth))
                continue

            identifier = find_first_node(node, 'interface_declaration', 'qualified_name')
            if identifier is None:
                identifier = find_first_node(node, 'class_declaration', 'identifier')
            if identifier is None:
                identifier = find_first_node(node, 'struct_declaration', 'identifier')
            if identifier is None:
                identifier = find_first_node(node, 'record_declaration', 'identifier')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = graph.new_symbol(ctx.parent, Category.TYPE, name, block)
                push(Context.new(symbol, depth))
                continue

            identifier = find_first_node(node, 'method_declaration', 'identifier')
            if identifier is None:
                identifier = find_first_node(node, 'constructor_declaration', 'identifier')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = graph.new_symbol(ctx.parent, Category.FUNCTION, name, block)
                push(Context.new(symbol, depth))
                continue

            if ctx.parent.category == Category.TYPE:
                identifier = find_first_node(node, 'field_declaration', 'variable_declaration', 'variable_declarator', 'identifier')
                if identifier is not None:
                    name = decode_normalize(identifier.text)
                    symbol = graph.new_symbol(ctx.parent, Category.VARIABLE, name, block)
                    push(Context.new(symbol, depth))
                    continue

            if node.type == 'identifier' and ctx.parent.category in NAMESPACE_AWARE_CATEGORIES:
                name = decode_normalize(node.text)
                if ctx.parent.name != name or ctx.parent.block.begin < block.begin:
                    ctx.parent.references.add(Reference.new(name, Category.TYPE))
                    ctx.parent.references.add(Reference.new(name, Category.FUNCTION))
                    ctx.parent.references.add(Reference.new(name, Category.VARIABLE))
                    continue

            # FIXME: Create references from static member variable initializers
