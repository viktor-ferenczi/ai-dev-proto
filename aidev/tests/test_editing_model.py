import unittest

from aidev.editing.model import Document, Block
from aidev.tests.data import SHOPPING_CART_CS


class TestEditingModel(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.maxDiff = None
        self.document = Document.from_text('ShoppingCart.cs', SHOPPING_CART_CS)

    def test_edit(self):
        doc = self.document
        hunk = doc.edit()

        code_block = hunk.get_code_block_for_editing(doc)
        print('\n'.join(code_block))
        self.assertTrue(code_block[0].startswith('['))
        self.assertTrue(code_block[0].endswith(']'))
        self.assertTrue('ShoppingCart' in code_block[0])
        self.assertEqual('```cs', code_block[1])
        self.assertEqual(SHOPPING_CART_CS, '\n'.join(code_block[2:-1]))
        self.assertEqual('```', code_block[-1])

        replacement = code_block[5:9]
        edited = hunk.substitute_placeholders(doc, replacement)
        self.assertEqual(4, len(edited))
        for edited_line, original_line in zip(edited, doc.lines[3:7]):
            self.assertEqual(original_line, edited_line)

    def test_edit_block(self):
        doc = self.document
        hunk = doc.edit_block(Block(begin=33, end=79))

        code_block = hunk.get_code_block_for_editing(doc)
        print('\n'.join(code_block))
        self.assertEqual(2 + (79 - 33) + 1, len(code_block))
        for doc_line, code_block_line in zip(doc.lines[33:79], code_block[2:-1]):
            self.assertEqual(doc_line, code_block_line)

        replacement = '''\
        public bool AddToCart(Food food, int amount)
        {
            if (food.InStock == 0 || amount == 0)
            {
                return false;
            }
            
            // Just stripping out the whole logic, because why not? :)

            _context.SaveChanges();
            return true;
        }
'''.replace('\r\n', '\n').split('\n')
        edited_doc = doc.apply_replacements({hunk.id: replacement})
        reference = '\n'.join(
            doc.lines[:33] +
            replacement +
            doc.lines[79:]
        )
        self.assertEquals(doc.path, edited_doc.path)
        self.assertEquals(doc.doctype, edited_doc.doctype)
        self.assertFalse(bool(edited_doc.hunks))
        self.assertEquals(reference, '\n'.join(edited_doc.lines))

    def test_placeholders(self):
        doc = self.document
        hunk = doc.edit_block(Block(begin=36, end=79))
        hunk.exclude_block(Block(begin=48, end=59))
        hunk.exclude_block(Block(begin=62, end=73))

        found = set()
        code_block = hunk.get_code_block_for_editing(doc)
        print('\n'.join(code_block))
        for line in code_block:
            for placholder in hunk.placeholders:
                if placholder.id in line:
                    self.assertNotIn(placholder.id, found)
                    found.add(placholder.id)
        self.assertEqual(2, len(found))

        replacement = '''\
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
                // PLACEHOLDER0
            }
            else
            {
                // PLACEHOLDER1
            }

            _context.SaveChanges();
            return true;
        }'''.replace('\r\n', '\n')
        for i, p in enumerate(hunk.placeholders):
            replacement = replacement.replace(f'PLACEHOLDER{i}', p.id)
        replacement = replacement.split('\n')

        edited_doc = doc.apply_replacements({})
        reference = list(doc.lines)
        self.assertEquals('\n'.join(reference), '\n'.join(edited_doc.lines))

        edited_doc = doc.apply_replacements({hunk.id: replacement})
        reference[77] = '            return true;'
        del reference[74]
        self.assertEquals(doc.path, edited_doc.path)
        self.assertEquals(doc.doctype, edited_doc.doctype)
        self.assertFalse(bool(edited_doc.hunks))
        self.assertEquals('\n'.join(reference), '\n'.join(edited_doc.lines))
