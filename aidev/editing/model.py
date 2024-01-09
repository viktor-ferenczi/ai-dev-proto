""" Source code and document editing for LLMs

Replacing entire source files for small changes is inefficient (performance,
context window limit) and error-prone (too much text to copy verbatim).

Reusing the established diff formats (unified, context) is not feasible, because
LLMs cannot deal with line numbers and gets confused by the fixed lines of context.

Differences based on AST or document structure (HTML, XML) are language specific,
complex and not widely used, therefore the LLMs are not expected to know about them.
There have been solutions in the early 2000's, but they have not been used widely.

The solution should be
- efficient with context size and inference time (should not require much text)
- non-confusing for LLMs by providing only (mostly) relevant information
- allow for uniquely identifying hunks
- allow for multiple disjunct hunks in the same source file
- quick to extract hunks
- quick to patch hunks with their replacements

Requirements about the edited text:
- Should not contain excessively long lines.
- Should not be longer than a million lines.
- Auto-formatted (normalized) before and after editing.
- Training whitespace and newline at the end of document are normalized.

A hunk is a related set of code or document lines, the unit of editing. Hunks
must not overlap. Hunks may have block of lines exluded from editing by replacing
them with placeholders.

LLMs are supposed to edit text (source code, templates) by replacing entire
hunks. No finer-grain editing is required, since hunks should already reflect
the minimum amount of text which is semantically meaningful.

Hunks are defined by:
- Hunk ID, unique within the conversation
- Path to the text file
- Block of text represented by a range of line numbers (indices)
- Placeholders to exclude blocks from LLM editing

The LLM can edit the hunk by stating the Hunk ID and providing the replacement
text in a code block. The LLM must reproduce all placeholders as-is in the right
positions to be consistent with the original code. Failing to reproduce any
placeholder in the replacement code is a validation error.

In case of programming languages with namespaces (C#, Java, C++, ...) the Hunk ID
may include additional information, for example: Namespace.Class.Method

In case of document files with an element hierarchy (HTML, XML, ...) the hunk must
contain a full element from its opening tag to its closing tag to be semantically
meaningful for the LLM. The document normalization after editing must also validate
the hierarchy to cache inconsistent changes breaking the document structure.

If a hunk includes lines which are irrelevant for the task at hand, then those parts
should be replaced by placeholders as long as they represent a significant saving on
context size or helps to avoid confusing the LLM.

The exact format of the placeholder is specific to the programming language or
document format, since it must preserve the validity of its sourrounding context.
The LLM must reproduce those placeholders verbatim, failing to do so is a validation
error. Placeholders must be on separate lines, but may have whitespace around them.
Placeholders must not hide (remove) any information which is used in the remaining
hunk visible for the LLM to avoid confusion.

Document model classes support the builder pattern. They are created and appended,
but never modified in place, nor any information removed from them until being deleted.

"""
import bisect
from typing import Any, Optional, Iterable

from pydantic import BaseModel

from aidev.common.util import read_text_file, SimpleEnum, write_text_file, copy_indent


class DocType(SimpleEnum):
    """Document type supported for editing by LLMs"""

    UNKNOWN = 'UNKNOWN'
    TEXT = 'TEXT'
    MARKDOWN = 'MARKDOWN'
    PYTHON = 'PYTHON'
    CSHARP = 'CSHARP'
    CSHTML = 'CSHTML'

    @classmethod
    def from_path(cls, path: str) -> 'DocType':
        extension = path.rsplit('.')[-1].lower()
        return cls.from_extension(extension)

    @classmethod
    def from_extension(cls, extension: str) -> 'DocType':
        return {
            'txt': cls.TEXT,
            'md': cls.MARKDOWN,
            'py': cls.PYTHON,
            'cs': cls.CSHARP,
            'cshtml': cls.CSHTML,
        }.get(extension, cls.UNKNOWN)

    @property
    def code_block_type(self) -> str:
        return {
            DocType.UNKNOWN: '',
            DocType.TEXT: '',
            DocType.MARKDOWN: 'md',
            DocType.PYTHON: 'py',
            DocType.CSHARP: 'cs',
            DocType.CSHTML: 'cshtml',
        }[self]


class Block(BaseModel):
    """Represent a block of consequtive lines of text"""

    begin: int
    """Zero-based index of the first line of the block (one less than line number)"""

    end: int
    """Zero-based index of the first line after the block (one less than line number)"""

    def is_overlapping(self, other: 'Block') -> bool:
        return self.begin < other.end and self.end > other.begin

    def is_inside(self, other: 'Block') -> bool:
        return self.begin >= other.begin and self.end <= other.end

    @staticmethod
    def insort(items: list[Any], item: Any, name: str):
        """Insertion sort for sorted list objects having a `block: Block` property
        """
        if item in items:  # pragma: no cover
            raise ValueError(f'This {name} has already been added: {item!r}')

        bisect.insort(items, item, key=lambda p: p.block.begin)

        i = items.index(item)

        if i > 0 and items[i - 1].is_overlapping(item):  # pragma: no cover
            raise ValueError(f'Overlapping {name}: {item!r}, {items[i - 1]!r}')

        if i + 1 < len(items) and item.is_overlapping(items[i + 1]):  # pragma: no cover
            raise ValueError(f'Overlapping {name}: {item!r}, {items[i + 1]!r}')


class Placeholder(BaseModel):
    """Block of lines to exclude from editing in a hunk"""

    id: str
    """Unique identifier within the conversation LLMs can reproduce verbatim"""

    block: Block
    """Block relative to the document"""

    def is_overlapping(self, other: 'Placeholder') -> bool:
        return self.block.is_overlapping(other.block)

    def format_id(self, doctype: DocType) -> str:
        formatter = {
            DocType.UNKNOWN: (lambda v: self.id),
            DocType.TEXT: (lambda v: self.id),
            DocType.MARKDOWN: (lambda v: f'`{self.id}`'),
            DocType.PYTHON: (lambda v: f'# {self.id}'),
            DocType.CSHARP: (lambda v: f'// {self.id}'),
            DocType.CSHTML: (lambda v: f'<!-- {self.id} -->'),
        }[doctype]
        return formatter(id)


class Hunk(BaseModel):
    """Block of lines to be edited inside a document"""

    id: str
    """Unique identifier within the conversation LLMs can reproduce verbatim"""

    block: Block
    """Block of lines in the document"""

    placeholders: list[Placeholder] = []
    """Sorted placeholders, they cannot overlap"""

    def add_placeholder(self, placeholder: Placeholder):
        if not placeholder.block.is_inside(self.block):  # pragma: no cover
            raise ValueError(f'The placeholder ({placeholder.block!r}) is not contained by the hunk ({self.block!r})')

        Block.insort(self.placeholders, placeholder, 'placeholder')

    def exclude_block(self, block: Block) -> Placeholder:
        placeholder = Placeholder(
            id=f'[PLACEHOLDER#{block.begin}:{block.end}]',
            block=block,
        )
        self.add_placeholder(placeholder)
        return placeholder

    def get_code_block_for_editing(self, document: 'Document') -> list[str]:
        lines = [
            self.id,
            f'```{document.doctype.code_block_type}'
        ]
        lines.extend(self.iter_lines_for_editing(document))
        lines.append('```')
        return lines

    def iter_lines_for_editing(self, document: 'Document') -> Iterable[str]:
        """Yields the text lines to be sent to the LLM for editing,
        placeholders are replaced with their formatted IDs as
        comments suitable for the document type
        """
        position = self.block.begin
        for placeholder in self.placeholders:

            # Text lines before the placeholder
            yield from document.lines[position:placeholder.block.begin]

            # Placeholder to match the indentation level of the excluded block
            formatted_id = placeholder.format_id(document.doctype)
            indent_example = ''
            excluded_lines = document.lines[placeholder.block.begin:placeholder.block.end]
            for line in excluded_lines:
                if indent_example:
                    if line.lstrip():
                        indent_example = line
                        break
                elif line:
                    indent_example = line
            yield copy_indent(indent_example, formatted_id)

            # Skip the original text lines behind the placeholder
            position = placeholder.block.end

        # Text lines after the last placeholder
        yield from document.lines[position:self.block.end]

    def substitute_placeholders(self, document: 'Document', replacement: list[str]) -> list[str]:
        """Substitutes the placeholders into the LLM provided replacement text lines

        Raises ValueError if any of the placeholders are missing.

        """
        placeholder_map = {p.id: p for p in self.placeholders}

        lines = []
        for line in replacement:
            for placeholder_id in placeholder_map:
                if placeholder_id in line:
                    placeholder = placeholder_map.pop(placeholder_id)
                    lines.extend(document.lines[placeholder.block.begin: placeholder.block.end])
                    break
            else:
                lines.append(line)

        if placeholder_map:  # pragma: no cover
            raise ValueError(f'Missing placeholders: {sorted(placeholder_map)!r}')

        return lines


class Document(BaseModel):
    """Document to be edited by LLMs"""

    path: str
    """Relative path of the document to the working copy"""

    doctype: DocType
    """Document type"""

    lines: list[str]
    """Lines of text without trailing newline"""

    hunks: list[Hunk] = []
    """Sorted hunks, they cannot overlap"""

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def is_valid_block(self, block: Block) -> bool:
        return 0 <= block.begin < block.end <= self.line_count

    def add_hunk(self, hunk: Hunk):
        Block.insort(self.hunks, hunk, 'hunk')

    def edit(self) -> Hunk:
        block = Block(begin=0, end=self.line_count)
        hunk = Hunk(
            id=f'[HUNK:{self.path}]',
            document=self,
            block=block,
        )

        self.add_hunk(hunk)
        return hunk

    def edit_block(self, block: Block) -> Hunk:
        if not self.is_valid_block(block):  # pragma: no cover
            raise ValueError(f'Invalid block for this document of {self.line_count} lines: {block!r}')

        hunk = Hunk(
            id=f'[HUNK:{self.path}#{block.begin}:{block.end}]',
            document=self,
            block=block,
        )

        self.add_hunk(hunk)
        return hunk

    @classmethod
    def from_file(cls, path: str) -> 'Document':
        text = read_text_file(path)
        return cls.from_text(path, text)

    @classmethod
    def from_text(cls, path: str, text: str) -> 'Document':
        doctype = DocType.from_path(path)
        lines: list[str] = text.split('\n')
        return cls(path=path, doctype=doctype, lines=lines)

    def write(self):
        write_text_file(self.path, '\n'.join(self.lines))

    def apply_replacements(self, replacements: dict[str, list[str]]) -> 'Document':
        """Applies replacements to the hunks requested

        Returns a new Document with the edited lines and no hunks.
        The path and the doctype are copied from the original document.

        Raises ValueError in case of an invalid hunk ID or a missing
        placeholder in any of the hunks processed.

        """
        replacements = dict(**replacements)

        lines = []
        position = 0
        for hunk in self.hunks:
            lines.extend(self.lines[position:hunk.block.begin])

            replacement: Optional[list[str]] = replacements.pop(hunk.id, None)
            if replacement is None:
                lines.extend(self.lines[hunk.block.begin:hunk.block.end])
            else:
                edited_lines = hunk.substitute_placeholders(self, replacement)
                lines.extend(edited_lines)

            position = hunk.block.end

        lines.extend(self.lines[position:])

        if replacements:  # pragma: no cover
            raise ValueError(f'Unknown hunk IDs: {list(replacements)!r}')

        edited_document = Document(
            path=self.path,
            doctype=self.doctype,
            lines=lines,
        )

        return edited_document
