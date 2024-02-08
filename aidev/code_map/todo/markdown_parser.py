import uuid
from typing import Iterator

from ..common.config import C
from ..common.util import decode_normalize
from ..common.util import tiktoken_len
from model.fragment import Fragment
from parsers.registrations import BaseParser
from splitters.markdown_splitter import MarkdownSplitter


# FIXME: Replace with proper parser
class MarkdownParser(BaseParser):
    name = 'Markdown'
    extensions = ('md',)
    mime_types = ('text/markdown',)

    splitter = MarkdownSplitter(
        chunk_size=C.MAX_TOKENS_PER_FRAGMENT,
        length_function=tiktoken_len
    )

    def parse(self, path: str, content: bytes) -> Iterator[Fragment]:
        text_content = decode_normalize(content)
        if not text_content.strip():
            return

        summary = []
        for sentence in self.splitter.split_text(text_content):

            yield Fragment(
                uuid=str(uuid.uuid4()),
                path=path,
                lineno=sentence.lineno,
                depth=sentence.depth,
                type='documentation',
                name='',
                text=sentence.text,
                tokens=tiktoken_len(sentence.text),
            )

            for line in sentence.text.split('\n'):
                if line.startswith('#'):
                    summary.append(f'{line}\n')

        if not summary:
            # TODO: Generate a summary using an LLM
            pass

        summary = ''.join(summary)
        yield Fragment(
            uuid=str(uuid.uuid4()),
            path=path,
            lineno=1,
            depth=0,
            type='summary',
            name='',
            text=''.join(summary),
            tokens=tiktoken_len(summary),
        )
