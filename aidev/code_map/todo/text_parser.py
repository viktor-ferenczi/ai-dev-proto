import uuid
from typing import Iterator

from ..common.config import C
from ..common.util import decode_normalize
from ..common.util import tiktoken_len
from model.fragment import Fragment
from parsers.base_parser import BaseParser
from ..splitters.text_splitter import TextSplitter
from ...common.util import count_lines


class TextParser(BaseParser):
    name = 'Text'
    extensions = ('txt',)
    mime_types = ('text/plain',)

    splitter = TextSplitter(
        chunk_size=C.MAX_TOKENS_PER_FRAGMENT,
        length_function=tiktoken_len
    )

    def parse(self, path: str, content: bytes) -> Iterator[Fragment]:
        text_content = decode_normalize(content)
        if not text_content.strip():
            return

        # Avoid single line JSON files and such, they are a CPU hog
        data_file = path.endswith('.json') or path.endswith('.csv') or path.endswith('.tsv') or path.endswith('.dsv')
        if not data_file:
            first_line_length = text_content.find('\n')
            line_count = count_lines(text_content)
            if first_line_length >= 0 and first_line_length < 1000 and line_count < 5000:
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

        # TODO: Generate a summary using an LLM
        summary = ''

        yield Fragment(
            uuid=str(uuid.uuid4()),
            path=path,
            lineno=1,
            depth=0,
            type='summary',
            name='',
            text=summary,
            tokens=tiktoken_len(summary),
        )
