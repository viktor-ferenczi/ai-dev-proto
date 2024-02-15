import unittest

from aidev.code_map.csharp_parser import CSharpParser
from aidev.code_map.cshtml_parser import CshtmlParser
from aidev.code_map.model import Graph
from aidev.code_map.parsers import init_tree_sitter
from aidev.tests.data import SHOPPING_CART_CS, DEFAULT_CSHTML


class TestParsers(unittest.TestCase):

    def setUp(self):
        init_tree_sitter()
        super().setUp()

    def test_csharp_parser(self):
        path = 'ShoppingCart.cs'
        graph = Graph.new()
        parser = CSharpParser()
        parser.parse(graph, path, SHOPPING_CART_CS.encode('utf-8'))
        parser.cross_reference(graph, path)
        print(graph.model_dump_json(indent=2))

    def test_cshtml_parser(self):
        path = 'Default.cshtml'
        graph = Graph.new()
        parser = CshtmlParser()
        parser.parse(graph, path, DEFAULT_CSHTML.encode('utf-8'))
        parser.cross_reference(graph, path)
        print(graph.model_dump_json(indent=2))
