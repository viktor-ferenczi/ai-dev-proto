import os
from typing import Set
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

    @classmethod
    def new(cls, parent: Symbol, relation: Relation, last_lineno: int) -> 'Context':
        return cls(parent=parent, relation=relation, last_lineno=last_lineno)


class CSharpParser(TreeSitterParser):
    name = 'CSharp'
    extensions = ('cs',)
    mime_types = ('text/x-csharp',)
    tree_sitter_language_name = 'c_sharp'

    def collect(self, graph: Graph, path: str, tree: Tree, file_line_count: int):
        source_basename = os.path.basename(path)
        source_name = os.path.splitext(source_basename)[0]
        source = Symbol.new(path, Category.SOURCE, Block.from_range(0, file_line_count), source_name)
        graph.add_symbol(source)

        ctx: Context = Context.new(source, Relation.PARENT, file_line_count - 1)
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

            while ctx.last_lineno < lineno:
                ctx = stack.pop()
                if self.debug:
                    print(f'CTX: {"> " * len(stack)}{pformat(ctx)}')

            identifier = find_first_node(node, 'using_directive', 'qualified_name')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = Symbol.new(path, Category.USING, block, name)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                push(Context.new(symbol, Relation.CHILD, last_lineno))
                continue

            identifier = find_first_node(node, 'namespace_declaration', 'qualified_name')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = Symbol.new(path, Category.NAMESPACE, block, name)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                push(Context.new(symbol, Relation.CHILD, last_lineno))
                continue

            identifier = find_first_node(node, 'interface_declaration', 'qualified_name')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = Symbol.new(path, Category.INTERFACE, block, name)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                push(Context.new(symbol, Relation.CHILD, last_lineno))
                continue

            identifier = find_first_node(node, 'class_declaration', 'identifier')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = Symbol.new(path, Category.CLASS, block, name)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                push(Context.new(symbol, Relation.CHILD, last_lineno))
                continue

            identifier = find_first_node(node, 'struct_declaration', 'identifier')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = Symbol.new(path, Category.STRUCT, block, name)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                push(Context.new(symbol, Relation.CHILD, last_lineno))
                continue

            identifier = find_first_node(node, 'record_declaration', 'identifier')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = Symbol.new(path, Category.RECORD, block, name)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                push(Context.new(symbol, Relation.CHILD, last_lineno))
                continue

            identifier = find_first_node(node, 'method_declaration', 'identifier')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = Symbol.new(path, Category.FUNCTION, block, name)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                push(Context.new(symbol, Relation.CHILD, last_lineno))
                continue

            identifier = find_first_node(node, 'constructor_declaration', 'identifier')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = Symbol.new(path, Category.FUNCTION, block, name)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                push(Context.new(symbol, Relation.CHILD, last_lineno))
                continue

            identifier = find_first_node(node, 'local_declaration_statement', 'variable_declaration', 'variable_declarator', 'identifier')
            if identifier is not None:
                name = decode_normalize(identifier.text)
                symbol = Symbol.new(path, Category.VARIABLE, block, name)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                continue

            if node.type.endswith('_statement') and ctx.parent.category != Category.STATEMENT:
                symbol = Symbol.new(path, Category.STATEMENT, block)
                graph.add_symbol_and_relation_both_ways(ctx.parent, ctx.relation, symbol)
                push(Context.new(symbol, Relation.CHILD, last_lineno))
                continue

            if node.type == 'identifier' and ctx.parent.category == Category.STATEMENT:
                statement = ctx.parent

                # Rough scoping rules to exclude surely inaccessible symbols.
                # It does not give exact accessibility, for example does not consider private or protected.

                parents: list[Symbol] = [
                    parent
                    for parent in graph.walk_related(statement, Relation.PARENT)
                    if parent.category in (Category.CLASS, Category.USING, Category.NAMESPACE, Category.SOURCE)
                ]

                # FIXME: Narrow down member and local variable access based on node.parent (member_access_expression, etc.)
                # FIXME: Narrow down type references based on node.parent (parameter, object_creation_expression)

                accessible: Set[Symbol] = set()
                for parent in parents:

                    # Map USING to NAMESPACE
                    if parent.category == Category.USING:
                        for symbol in graph.symbols.values():
                            if symbol.category == Category.NAMESPACE and symbol.name == parent.name:
                                parent = symbol
                                break
                        else:
                            continue

                    accessible.update(graph.walk_related(parent, Relation.CHILD))

                name = decode_normalize(node.text)
                for symbol in graph.symbols.values():
                    if symbol.name == name and symbol in accessible:
                        graph.add_relation_both_ways(statement, Relation.USES, symbol)
