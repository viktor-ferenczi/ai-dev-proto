import unittest

from aidev.code_map.csharp_parser import CSharpParser
from aidev.code_map.model import Graph
from aidev.tests.data import SHOPPING_CART_CS


class TestCSharpParser(unittest.TestCase):

    def test_code_map(self):
        graph = Graph.new()

        parser = CSharpParser()
        parser.parse(graph, 'ShoppingCart.cs', SHOPPING_CART_CS.encode('utf-8'))

        print(graph.model_dump_json(indent=2))
