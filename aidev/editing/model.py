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
them with markers.

LLMs are supposed to edit text (source code, templates) by replacing entire
hunks. No finer-grain editing is required, since hunks should already reflect
the minimum amount of text which is semantically meaningful.

Hunks are defined by:
- Hunk ID, unique within the conversation
- Path to the text file
- Block of text represented by a range of line numbers (indices)
- Placeholders to exclude blocks from LLM editing

The LLM can edit the hunk by stating the Hunk ID and providing the replacement
text in a code block. The LLM must reproduce all markers as-is in the right
positions to be consistent with the original code. Failing to reproduce any
marker in the replacement code is a validation error.

In case of programming languages with namespaces (C#, Java, C++, ...) the Hunk ID
may include additional information, for example: Namespace.Class.Method

In case of document files with an element hierarchy (HTML, XML, ...) the hunk must
contain a full element from its opening tag to its closing tag to be semantically
meaningful for the LLM. The document normalization after editing must also validate
the hierarchy to cache inconsistent changes breaking the document structure.

If a hunk includes lines which are irrelevant for the task at hand, then those parts
should be replaced by markers as long as they represent a significant saving on
context size or helps to avoid confusing the LLM.

The exact format of the marker is specific to the programming language or
document format, since it must preserve the validity of its sourrounding context.
The LLM must reproduce those markers verbatim, failing to do so is a validation
error. Placeholders must be on separate lines, but may have whitespace around them.
Placeholders must not hide (remove) any information which is used in the remaining
hunk visible for the LLM to avoid confusion.

Document model classes support the builder pattern. They are created and appended,
but never modified in place, nor any information removed from them until being deleted.

"""
import bisect
from itertools import pairwise
from typing import Optional, Iterable

from pydantic import BaseModel

from aidev.common.util import read_text_file, SimpleEnum, write_text_file, copy_indent, join_lines, extract_code_blocks, replace_tripple_backquote


class DocType(str, SimpleEnum):
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


MARKER_NAME = 'AiDev.Marker'


class Block(BaseModel):
    """Represent a block of consequtive lines of text in a document
    """

    begin: int
    """Zero-based index of the first line of the block (one less than line number)"""

    end: int
    """Zero-based index of the first line after the block (one less than line number)"""

    @property
    def line_count(self):
        return self.end - self.begin

    @classmethod
    def from_range(cls, begin: int, end: int):
        if not (0 <= begin <= end):
            raise ValueError(f'Invalid block range: begin={begin}, end={end}')
        return cls(begin=begin, end=end)

    def is_overlapping(self, other: 'Block') -> bool:
        return self.begin < other.end and self.end > other.begin

    def is_inside(self, other: 'Block') -> bool:
        return self.begin >= other.begin and self.end <= other.end

    def format_marker(self, doctype: DocType) -> str:
        formatter = {
            DocType.UNKNOWN: (lambda: f'**{MARKER_NAME}#{self.begin}:{self.end}**'),
            DocType.TEXT: (lambda: f'**{MARKER_NAME}#{self.begin}:{self.end}**'),
            DocType.MARKDOWN: (lambda: f'**{MARKER_NAME}#{self.begin}:{self.end}**'),
            DocType.PYTHON: (lambda: f'{MARKER_NAME}("{self.begin}:{self.end}")'),
            DocType.CSHARP: (lambda: f'{MARKER_NAME}("{self.begin}:{self.end}");'),
            DocType.CSHTML: (lambda: f'<span class="{MARKER_NAME}">{self.begin}:{self.end}</span>'),
        }[doctype]
        return formatter()


def insort_block(blocks: list[Block], block: Block):
    """Insertion sort for sorted list of blocks
    """
    if block in blocks:  # pragma: no cover
        raise ValueError(f'This block has already been added: {block!r}')

    bisect.insort(blocks, block, key=lambda p: p.begin)

    i = blocks.index(block)

    if i > 0 and blocks[i - 1].is_overlapping(block):  # pragma: no cover
        raise ValueError(f'Overlapping block: {block!r}, {blocks[i - 1]!r}')

    if i + 1 < len(blocks) and block.is_overlapping(blocks[i + 1]):  # pragma: no cover
        raise ValueError(f'Overlapping block: {block!r}, {blocks[i + 1]!r}')


class Document(BaseModel):
    """Document (source code)
    """

    path: str
    """Relative path of the document to the working copy"""

    doctype: DocType
    """Document type"""

    lines: list[str]
    """Lines of text without trailing newline"""

    @property
    def id(self) -> str:
        """Unique identifier within the conversation LLMs can reproduce verbatim"""
        return f'[SOURCE:{self.path}]'

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def text(self) -> str:
        return join_lines(self.lines)

    @property
    def code_block(self) -> str:
        return f'```{self.doctype.code_block_type}\n{replace_tripple_backquote(self.text)}\n```'

    @property
    def code_block_lines(self) -> list[str]:
        lines = [f'```{self.doctype.code_block_type}']
        lines.extend(self.lines)
        lines.append('```')
        return lines

    @classmethod
    def from_file(cls, path: str) -> 'Document':
        text = read_text_file(path)
        return cls.from_text(path, text)

    @classmethod
    def from_text(cls, path: str, text: str) -> 'Document':
        doctype = DocType.from_path(path)
        lines: list[str] = text.split('\n')
        return cls(path=path, doctype=doctype, lines=lines)

    def write(self) -> None:
        """Writes the document

        Overwrites the file on disk is it exists.

        """
        write_text_file(self.path, join_lines(self.lines))


class Hunk(BaseModel):
    """Block of lines to be edited inside a document"""

    document: Document
    """Document the hunk is defined for"""

    block: Block
    """Block of lines in the document"""

    markers: list[Block] = []
    """Sorted markers, they cannot overlap"""

    replacement: Optional[list[str]] = None
    """Replacement text for the hunk, potentially including markers"""

    @property
    def id(self) -> str:
        """Unique identifier within the conversation LLMs can reproduce verbatim"""
        return f'[HUNK:{self.document.path}#{self.block.begin}:{self.block.end}]'

    @property
    def lines(self) -> list[str]:
        return list(self.__iter_code_with_markers())

    @property
    def text(self) -> str:
        return join_lines(self.lines)

    @property
    def code_block(self) -> str:
        return f'```{self.document.doctype.code_block_type}\n{replace_tripple_backquote(self.text)}\n```'

    @property
    def code_block_lines(self) -> list[str]:
        lines = [f'```{self.document.doctype.code_block_type}']
        lines.extend(self.lines)
        lines.append('```')
        return lines

    @classmethod
    def from_document(cls, document: Document, block: Optional[Block] = None) -> 'Hunk':
        if block is None:
            block = Block.from_range(0, document.line_count)
        return cls(document=document, block=block)

    def is_overlapping(self, other: 'Hunk') -> bool:
        return self.block.is_overlapping(other.block)

    def add_marker(self, marker: Block) -> None:
        if not marker.is_inside(self.block):  # pragma: no cover
            raise ValueError(f'The marker ({marker!r}) is not contained by the hunk ({self.block!r})')

        insort_block(self.markers, marker)

    def exclude_block(self, block: Block) -> None:
        self.add_marker(block)

    def __iter_code_with_markers(self) -> Iterable[str]:
        """Yields the text lines to be sent to the LLM for editing,
        markers are replaced with their formatted IDs as
        comments suitable for the document type
        """
        doc = self.document
        original_lines = doc.lines

        position = self.block.begin
        for marker in self.markers:

            # Text lines before the marker
            yield from original_lines[position:marker.begin]

            # Placeholder to match the indentation level of the excluded block
            formatted_marker = marker.format_marker(doc.doctype)
            indent_example = ''
            excluded_lines = original_lines[marker.begin:marker.end]
            for line in excluded_lines:
                if indent_example:
                    if line.lstrip():
                        indent_example = line
                        break
                elif line:
                    indent_example = line
            yield copy_indent(indent_example, formatted_marker)

            # Skip the original text lines behind the marker
            position = marker.end

        # Text lines after the last marker
        yield from original_lines[position:self.block.end]

    def apply_replacement(self) -> list[str]:
        """Applies the replacement by substituting markers

        If no replacement is provided then it returns the original
        code lines from the hunk.

        Allows removing code by excluding markers, therefore having
        full test coverage is important to detect any erroneous removal.

        """
        original_lines = self.document.lines
        if self.replacement is None:
            return original_lines[self.block.begin: self.block.end]

        doctype = self.document.doctype
        marker_map = {p.format_marker(doctype): p for p in self.markers}

        lines = []
        for line in self.replacement:
            for marker_id in marker_map:
                if marker_id in line:
                    marker = marker_map.pop(marker_id)
                    lines.extend(original_lines[marker.begin: marker.end])
                    break
            else:
                lines.append(line)

        return lines


class Patch(BaseModel):
    """Modifications to hunks in a document
    """

    document: Document
    """Original document"""

    hunks: list[Hunk]
    """Hunks to apply"""

    @classmethod
    def from_hunks(cls, document: Document, hunks: list[Hunk]):
        return cls(document=document, hunks=hunks)

    def apply(self) -> Document:
        """Applies the replacements from all the hunks

        Sorts the hunks and ensure that they are disjunct.

        Returns a new Document with the edited lines and no hunks.
        The path and the doctype are copied from the original document.

        Raises ValueError if any of the hunks overlap.

        """
        self.__sort_and_verify_hunks()
        lines: list[str] = self.__apply_sorted_hunks()
        return Document(
            path=self.document.path,
            doctype=self.document.doctype,
            lines=lines,
        )

    def __sort_and_verify_hunks(self) -> None:
        if not self.hunks:
            return

        self.hunks.sort(key=lambda h: h.block.begin)

        if self.hunks[0].block.begin < 0:
            raise ValueError(f'Hunk is outside of the document: {self.hunks[0].id}, line_count={self.document.line_count}')

        if self.hunks[-1].block.end > self.document.line_count:
            raise ValueError(f'Hunk is outside of the document: {self.hunks[-1].id}, line_count={self.document.line_count}')

        for a, b in pairwise(self.hunks):
            if a.is_overlapping(b):
                raise ValueError(f'Overlapping hunks: {a.id}, {b.id}')

    def __apply_sorted_hunks(self) -> list[str]:
        original_lines = self.document.lines

        lines: list[str] = []

        position: int = 0
        for hunk in self.hunks:
            lines.extend(original_lines[position:hunk.block.begin])
            lines.extend(hunk.apply_replacement())
            position = hunk.block.end

        lines.extend(original_lines[position:])
        return lines

    @classmethod
    def from_completion(cls,
                        document: Document,
                        completion: str,
                        ) -> 'Patch':
        hunks: list[Hunk] = []
        for code_block in extract_code_blocks(completion):

            if not code_block.strip():
                continue

            code_lines: list[str] = code_block.split('\n')

            start = 0
            while start < len(code_lines):
                for block in iter_find_partial_blocks(document.lines, 0, code_lines, start):
                    hunk = Hunk.from_document(document, block)
                    hunks.append(hunk)
                    start += block.line_count
                    break
                else:
                    raise ValueError(f'Code lines not found {start}:{len(code_lines)}')

        return cls(document=document, hunks=hunks)

    def merge_hunks(self):
        if len(self.hunks) <= 1:
            return

        original_lines = self.document.lines

        self.__sort_and_verify_hunks()

        start = min(h.block.begin for h in self.hunks)
        end = max(h.block.end for h in self.hunks)

        hunk = Hunk.from_document(self.document, Block.from_range(start, end))
        for a, b in pairwise(h.block for h in self.hunks):
            if a.end == b.begin:
                continue

            block = Block.from_range(a.end, b.begin)
            if not join_lines(original_lines[a.end: b.begin]).strip():
                continue

            hunk.add_marker(block)

        self.hunks[:] = [hunk]


def iter_find_partial_blocks(
        doc: list[str],
        doc_start: int,
        block: list[str],
        block_start: int,
) -> Iterable[Block]:
    assert doc_start >= 0
    assert block_start >= 0

    doc_len = len(doc)
    block_len = len(block)

    if doc_start >= doc_len or block_start >= block_len:
        return

    j = block_start
    for i in range(doc_start, doc_len):

        doc_line = doc[i]
        if doc_line != block[j]:
            continue

        remaining = min(doc_len - i, block_len - j)
        for k in range(remaining):
            if doc[i + k] != block[j + k]:
                yield Block.from_range(i, i + k)
                j += k
                break
        else:
            yield Block.from_range(i, i + remaining)
            break
