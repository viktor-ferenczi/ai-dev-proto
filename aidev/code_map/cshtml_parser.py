from pprint import pformat
from typing import List

from pydantic import BaseModel
from tree_sitter import Tree, TreeCursor

from .tree_sitter_util import walk_nodes, find_first_node
from .model import CodeMap, Symbol, Category, Block, Reference
from .tree_sitter_parser import TreeSitterParser
from ..common.util import decode_normalize


class Context(BaseModel):
    parent: Symbol
    depth: int

    @classmethod
    def new(cls, parent: Symbol, depth: int) -> 'Context':
        return cls(parent=parent, depth=depth)


class CshtmlParser(TreeSitterParser):
    name = 'Cshtml'
    extensions = ('cshtml',)
    mime_types = ('text/x-cshtml',)
    tree_sitter_language_name = 'html'

    def collect(self, graph: CodeMap, path: str, tree: Tree, file_line_count: int):
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

            if node.type == 'text' and ctx.parent.category == Category.SOURCE:
                text = decode_normalize(node.text)
                if text.startswith('@model '):
                    name = text.split(' ', 1)[1].strip()
                    symbol = graph.new_symbol(ctx.parent, Category.USING, name, block)
                    continue

            start_tag = find_first_node(node, 'element', 'start_tag')
            if start_tag is not None:
                tag_name = find_first_node(start_tag, 'start_tag', 'tag_name')
                assert tag_name is not None
                name = decode_normalize(tag_name.text)
                symbol = graph.new_symbol(ctx.parent, Category.BLOCK, name, block)
                push(Context.new(symbol, depth))
                continue

            # Attributes of:
            # @model Shop.Web.Models.Food.FoodIndexModel
            # <a asp-controller="Category" asp-action="Topic" asp-route-id="@Model.CategoryId" class="btn btn-back">Back to @Model.CategoryName section</a>
            # <a asp-action="Profile" asp-controller="Account" asp-route-userId="@order.UserId">@order.UserFullName</a>

            attribute_name = find_first_node(node, 'attribute', 'attribute_name')
            if attribute_name is None:
                continue

            qval = find_first_node(node, 'attribute', 'quoted_attribute_value')
            if qval is None:
                continue

            name = decode_normalize(attribute_name.text)
            attribute = graph.new_symbol(ctx.parent, Category.BLOCK, name, block)
            push(Context.new(attribute, depth))

            # An action is a method of the Controller class named by the asp-controller
            if name.lower() == 'asp-action':
                attribute_value = find_first_node(qval, 'quoted_attribute_value', 'attribute_value')
                action_function_name = decode_normalize(attribute_value.text)
                ctx.parent.references.add(Reference.new(action_function_name, Category.FUNCTION))
                continue

            # Name of the controller class without the "Controller" suffix (naming convention)
            if name.lower() == 'asp-controller':
                attribute_value = find_first_node(qval, 'quoted_attribute_value', 'attribute_value')
                controller_class_name = decode_normalize(attribute_value.text)
                ctx.parent.references.add(Reference.new(f'{controller_class_name}Controller', Category.TYPE))
                continue

            # Routes to data from a model variable, reference only the data member.
            # See also: @Model, @model and template variables)
            if name.lower() == 'asp-route-':
                attribute_value = find_first_node(qval, 'quoted_attribute_value', 'attribute_value')
                model_variable_reference = decode_normalize(attribute_value.text)
                if '.' in model_variable_reference:
                    model_variable_name = model_variable_reference.split('.', 1)[1]
                    ctx.parent.references.add(Reference.new(model_variable_name, Category.TYPE))
