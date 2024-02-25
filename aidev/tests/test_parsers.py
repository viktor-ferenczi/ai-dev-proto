import unittest

from aidev.code_map.csharp_parser import CSharpParser
from aidev.code_map.cshtml_parser import CshtmlParser
from aidev.code_map.model import CodeMap
from aidev.code_map.parsers import init_tree_sitter
from aidev.tests import data


class TestParsers(unittest.TestCase):

    def setUp(self):
        init_tree_sitter()
        super().setUp()

    def test_csharp_enum(self):
        path = 'OrderBy.cs'
        code_map = CodeMap.new()
        parser = CSharpParser()
        parser.parse(code_map, path, data.ORDER_BY_CS.encode('utf-8'))
        code_map.cross_reference()
        print(code_map.model_dump_json(indent=2))

    def test_csharp_interface(self):
        path = 'IOrder.cs'
        code_map = CodeMap.new()
        parser = CSharpParser()
        parser.parse(code_map, path, data.IORDER_CS.encode('utf-8'))
        code_map.cross_reference()
        print(code_map.model_dump_json(indent=2))

    def test_csharp_class(self):
        path = 'ShoppingCart.cs'
        code_map = CodeMap.new()
        parser = CSharpParser()
        parser.parse(code_map, path, data.SHOPPING_CART_CS.encode('utf-8'))
        code_map.cross_reference()
        print(code_map.model_dump_json(indent=2))

    def test_csharp_property(self):
        path = 'CategoryIndexModel.cs'
        code_map = CodeMap.new()
        parser = CSharpParser()
        parser.parse(code_map, path, data.CATEGORY_INDEX_MODEL_CS.encode('utf-8'))
        code_map.cross_reference()
        print(code_map.model_dump_json(indent=2))

    def test_cshtml_parser(self):
        path = 'Default.cshtml'
        code_map = CodeMap.new()
        parser = CshtmlParser()
        parser.parse(code_map, path, data.DEFAULT_CSHTML.encode('utf-8'))
        code_map.cross_reference()
        print(code_map.model_dump_json(indent=2))
