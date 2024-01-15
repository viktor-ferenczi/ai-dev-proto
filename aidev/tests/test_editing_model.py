import unittest
from typing import Set

from aidev.common.util import join_lines
from aidev.editing.model import Document, Block, Hunk, Changeset
from aidev.tests.data import SHOPPING_CART_CS, ADD_TO_CARD_TODO


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

        self.assertEqual(SHOPPING_CART_CS, join_lines(doc.lines))

        code_block = doc.get_code()
        print(join_lines(code_block))

        self.assertEqual('[SOURCE:ShoppingCart.cs]', code_block[0])
        self.assertEqual('```cs', code_block[1])
        self.assertEqual(SHOPPING_CART_CS, join_lines(code_block[2:-1]))
        self.assertEqual('```', code_block[-1])

    def test_empty_changeset(self):
        doc = self.document
        changeset = Changeset.from_hunks(doc, [])
        edited_doc = changeset.apply()
        self.assertEqual(join_lines(doc.lines), join_lines(edited_doc.lines))

    def test_edit_no_change(self):
        doc = self.document

        def check(hunks: list[Hunk]):
            changeset = Changeset.from_hunks(doc, hunks)
            edited_doc = changeset.apply()
            self.assertEqual(join_lines(doc.lines), join_lines(edited_doc.lines))

        check([Hunk.from_document(doc)])

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

        def check(hunks: list[Hunk]):
            changeset = Changeset.from_hunks(doc, hunks)
            self.assertRaises(ValueError, changeset.apply)

        check([Hunk.from_document(doc, Block.from_range(0, doc.line_count + 1))])

        check([Hunk.from_document(doc, Block.from_range(0, 51)),
               Hunk.from_document(doc, Block.from_range(50, doc.line_count))])

        check([Hunk.from_document(doc, Block.from_range(0, 20)),
               Hunk.from_document(doc, Block.from_range(20, 30)),
               Hunk.from_document(doc, Block.from_range(29, doc.line_count))])

    def test_edit_full_document(self):
        doc = self.document

        hunk = Hunk.from_document(doc)

        code_block = hunk.get_code()
        self.assertEqual(f'[HUNK:ShoppingCart.cs#0:{doc.line_count}]', code_block[0])
        self.assertEqual('```cs', code_block[1])
        self.assertEqual(SHOPPING_CART_CS, join_lines(code_block[2:-1]))
        self.assertEqual('```', code_block[-1])

        hunk.replacement = doc.lines[::-1]
        changeset = Changeset.from_hunks(doc, [hunk])
        edited_doc = changeset.apply()
        self.assertEqual(join_lines(hunk.replacement), join_lines(edited_doc.lines))

    def test_edit_block(self):
        doc = self.document

        hunk = Hunk.from_document(doc, Block.from_range(33, 79))

        code_block = hunk.get_code()
        self.assertEqual(f'[HUNK:ShoppingCart.cs#33:79]', code_block[0])
        self.assertEqual('```cs', code_block[1])
        self.assertEqual(join_lines(doc.lines[33:79]), join_lines(code_block[2:-1]))
        self.assertEqual('```', code_block[-1])

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

        changeset = Changeset(document=doc, hunks=[hunk])
        edited_doc = changeset.apply()
        reference = join_lines(
            doc.lines[:33] +
            hunk.replacement +
            doc.lines[79:]
        )
        self.assertEqual(doc.path, edited_doc.path)
        self.assertEqual(doc.doctype, edited_doc.doctype)
        self.assertEqual(reference, join_lines(edited_doc.lines))

    def test_placeholders(self):
        doc = self.document

        hunk = Hunk.from_document(doc, Block.from_range(36, 79))
        hunk.exclude_block(Block.from_range(48, 59))
        hunk.exclude_block(Block.from_range(62, 73))

        found: Set[str] = set()
        code_block = hunk.get_code()
        print(join_lines(code_block))
        for line in code_block:
            for placholder in hunk.placeholders:
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
        for i, p in enumerate(hunk.placeholders):
            marker = p.format_marker(doc.doctype)
            replacement = replacement.replace(f'MARKER{i}', marker)
        hunk.replacement = replacement.split('\n')

        changeset = Changeset(document=doc, hunks=[])
        edited_doc = changeset.apply()
        reference = list(doc.lines)
        self.assertEqual(join_lines(reference), join_lines(edited_doc.lines))

        changeset = Changeset(document=doc, hunks=[hunk])
        edited_doc = changeset.apply()
        reference[77] = '            return true;'
        del reference[74]
        self.assertEqual(doc.path, edited_doc.path)
        self.assertEqual(doc.doctype, edited_doc.doctype)
        self.assertEqual(join_lines(reference), join_lines(edited_doc.lines))

    def test_parse_completion(self):
        doc = self.document
        changeset = Changeset.from_completion_lax(doc, ADD_TO_CARD_TODO)

        for hunk in changeset.hunks:
            print(join_lines(hunk.get_code()))
            print()

        self.assertEqual(4, len(changeset.hunks))
        self.assertEqual(Block.from_range(36, 62), changeset.hunks[0].block)
        self.assertEqual(Block.from_range(63, 69), changeset.hunks[1].block)
        self.assertEqual(Block.from_range(70, 75), changeset.hunks[2].block)
        self.assertEqual(Block.from_range(76, 79), changeset.hunks[3].block)

        changeset.merge_hunks()
        self.assertEqual(1, len(changeset.hunks))
        hunk = changeset.hunks[0]
        self.assertEqual(Block.from_range(36, 79), hunk.block)
        self.assertEqual(2, len(hunk.placeholders))
        self.assertEqual(Block.from_range(62, 63), hunk.placeholders[0])
        self.assertEqual(Block.from_range(69, 70), hunk.placeholders[1])

        print('-' * 40)
        print('Merged')
        print('-' * 40)
        print(join_lines(hunk.get_code()))
