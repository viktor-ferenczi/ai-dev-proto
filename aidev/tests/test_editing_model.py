import json
import unittest
from typing import Set, List

from aidev.common.util import join_lines
from aidev.editing.model import Document, Block, Hunk, Patch
from aidev.tests.data import SHOPPING_CART_CS, ADD_TO_CARD_TODO, REGRESSION_DOCUMENT_JSON, REGRESSION_COMPLETION


class TestEditingModel(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.maxDiff = None
        self.document = Document.from_text('ShoppingCart.cs', SHOPPING_CART_CS)

    def test_block(self):
        empty = Block.from_range(0, 0)
        self.assertEqual(0, empty.begin)
        self.assertEqual(0, empty.end)

        empty = Block.from_range(5, 5)
        self.assertEqual(5, empty.begin)
        self.assertEqual(5, empty.end)

        nine_lines = Block.from_range(0, 9)
        self.assertEqual(0, nine_lines.begin)
        self.assertEqual(9, nine_lines.end)

        def check(begin: int, end: int):
            self.assertRaises(ValueError, lambda: Block.from_range(begin, end))

        check(-2, -1)
        check(-1, -2)
        check(-1, 3)
        check(1, 0)

    def test_document(self):
        doc = self.document

        self.assertEqual(f'[SOURCE:{doc.path}]', doc.id)

        self.assertEqual(SHOPPING_CART_CS, join_lines(doc.lines))

        print(join_lines(doc.code_block))

        code_block_lines = doc.code_block_lines
        self.assertEqual('```cs', code_block_lines[0])
        self.assertEqual(SHOPPING_CART_CS, join_lines(code_block_lines[1:-1]))
        self.assertEqual('```', code_block_lines[-1])

    def test_empty_changeset(self):
        doc = self.document
        patch = Patch.from_hunks(doc, [])
        edited_doc = patch.apply()
        self.assertEqual(join_lines(doc.lines), join_lines(edited_doc.lines))

    def test_edit_no_change(self):
        doc = self.document

        def check(hunks: List[Hunk]):
            patch = Patch.from_hunks(doc, hunks)
            edited_doc = patch.apply()
            self.assertEqual(join_lines(doc.lines), join_lines(edited_doc.lines))

        hunk = Hunk.from_document(doc)
        check([hunk])

        self.assertEqual(f'[HUNK:{doc.path}#{hunk.block.begin}:{hunk.block.end}]', hunk.id)

        check([Hunk.from_document(doc, Block.from_range(0, 50)),
               Hunk.from_document(doc, Block.from_range(50, doc.line_count))])

        check([Hunk.from_document(doc, Block.from_range(0, 20)),
               Hunk.from_document(doc, Block.from_range(20, 30)),
               Hunk.from_document(doc, Block.from_range(30, doc.line_count))])

        check([Hunk.from_document(doc, Block.from_range(0, 20)),
               Hunk.from_document(doc, Block.from_range(25, 37)),
               Hunk.from_document(doc, Block.from_range(50, doc.line_count))])

    def test_edit_invalid_hunks(self):
        doc = self.document

        def check(hunks: List[Hunk]):
            patch = Patch.from_hunks(doc, hunks)
            self.assertRaises(ValueError, patch.apply)

        check([Hunk.from_document(doc, Block.from_range(0, doc.line_count + 1))])

        check([Hunk.from_document(doc, Block.from_range(0, 51)),
               Hunk.from_document(doc, Block.from_range(50, doc.line_count))])

        check([Hunk.from_document(doc, Block.from_range(0, 20)),
               Hunk.from_document(doc, Block.from_range(20, 30)),
               Hunk.from_document(doc, Block.from_range(29, doc.line_count))])

    def test_edit_full_document(self):
        doc = self.document

        hunk = Hunk.from_document(doc)

        code_block_lines = hunk.code_block_lines
        self.assertEqual('```cs', code_block_lines[0])
        self.assertEqual(SHOPPING_CART_CS, join_lines(code_block_lines[1:-1]))
        self.assertEqual('```', code_block_lines[-1])

        hunk.replacement = doc.lines[::-1]
        patch = Patch.from_hunks(doc, [hunk])
        edited_doc = patch.apply()
        self.assertEqual(join_lines(hunk.replacement), join_lines(edited_doc.lines))

    def test_edit_block(self):
        doc = self.document

        hunk = Hunk.from_document(doc, Block.from_range(33, 79))

        code_block_lines = hunk.code_block_lines
        self.assertEqual('```cs', code_block_lines[0])
        self.assertEqual(join_lines(doc.lines[33:79]), join_lines(code_block_lines[1:-1]))
        self.assertEqual('```', code_block_lines[-1])

        hunk.replacement = '''\
        public bool AddToCart(Food food, int amount)
        {
            if (food.InStock == 0 || amount == 0)
            {
                return false;
            }
            
            // Just stripping out the whole logic

            _context.SaveChanges();
            return true;
        }
'''.replace('\r\n', '\n').split('\n')

        patch = Patch(document=doc, hunks=[hunk])
        edited_doc = patch.apply()
        reference = join_lines(
            doc.lines[:33] +
            hunk.replacement +
            doc.lines[79:]
        )
        self.assertEqual(doc.path, edited_doc.path)
        self.assertEqual(doc.doctype, edited_doc.doctype)
        self.assertEqual(reference, join_lines(edited_doc.lines))

    def test_markers(self):
        doc = self.document

        hunk = Hunk.from_document(doc, Block.from_range(36, 79))
        hunk.exclude_block(Block.from_range(48, 59))
        hunk.exclude_block(Block.from_range(62, 73))

        found: Set[str] = set()
        print(join_lines(hunk.code_block))
        for line in hunk.code_block_lines:
            for placholder in hunk.markers:
                marker = placholder.format_marker(doc.doctype)
                if marker in line:
                    self.assertNotIn(marker, found)
                    found.add(marker)
        self.assertEqual(2, len(found))

        replacement: str = '''\
        public bool AddToCart(Food food, int amount)
        {
            if (food.InStock == 0 || amount == 0)
            {
                return false;
            }

            var shoppingCartItem = _context.ShoppingCartItems.SingleOrDefault(
                s => s.Food.Id == food.Id && s.ShoppingCartId == Id);
            var isValidAmount = true;
            if (shoppingCartItem == null)
            {
                MARKER0
            }
            else
            {
                MARKER1
            }

            _context.SaveChanges();
            return true;
        }'''.replace('\r\n', '\n')
        for i, p in enumerate(hunk.markers):
            marker = p.format_marker(doc.doctype)
            replacement = replacement.replace(f'MARKER{i}', marker)
        hunk.replacement = replacement.split('\n')

        patch = Patch(document=doc, hunks=[])
        edited_doc = patch.apply()
        reference = list(doc.lines)
        self.assertEqual(join_lines(reference), join_lines(edited_doc.lines))

        patch = Patch(document=doc, hunks=[hunk])
        edited_doc = patch.apply()
        reference[77] = '            return true;'
        del reference[74]
        self.assertEqual(doc.path, edited_doc.path)
        self.assertEqual(doc.doctype, edited_doc.doctype)
        self.assertEqual(join_lines(reference), join_lines(edited_doc.lines))

    def test_parse_completion(self):
        doc = self.document
        patch = Patch.from_completion(doc, ADD_TO_CARD_TODO)

        for hunk in patch.hunks:
            print(hunk.code_block)
            print()

        self.assertEqual(4, len(patch.hunks))
        self.assertEqual(Block.from_range(35, 62), patch.hunks[0].block)
        self.assertEqual(Block.from_range(63, 69), patch.hunks[1].block)
        self.assertEqual(Block.from_range(70, 75), patch.hunks[2].block)
        self.assertEqual(Block.from_range(75, 79), patch.hunks[3].block)

        patch.merge_hunks()
        self.assertEqual(1, len(patch.hunks))
        hunk = patch.hunks[0]
        self.assertEqual(Block.from_range(35, 79), hunk.block)
        self.assertEqual(2, len(hunk.markers))
        self.assertEqual(Block.from_range(62, 63), hunk.markers[0])
        self.assertEqual(Block.from_range(69, 70), hunk.markers[1])

        print('-' * 40)
        print('Merged')
        print('-' * 40)
        print(hunk.code_block)

    def test_regression_overlapping_hunks(self):
        document = Document(**json.loads(REGRESSION_DOCUMENT_JSON))
        patch = Patch.from_completion(document, REGRESSION_COMPLETION)
        patch.merge_hunks()
        print(patch.hunks[0].code_block)
