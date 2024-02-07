import json
import os
import shutil
import sys
from typing import Optional, Type

from magic import Magic, MagicException
from tree_sitter import Language

from .base_parser import PARSERS, BaseParser

INITIALIZED = False


def init_tree_sitter():
    global INITIALIZED

    if INITIALIZED:
        return

    map_parser_classes()
    build_tree_sitter_library()
    set_tree_sitter_languages()


PARSERS_BY_NAME = {}
PARSERS_BY_EXTENSION = {}
PARSERS_BY_MIME_TYPE = {}


def map_parser_classes():
    for parser_cls in PARSERS:
        assert issubclass(parser_cls, BaseParser)

        assert parser_cls.name not in PARSERS_BY_NAME, parser_cls.name
        PARSERS_BY_NAME[parser_cls.name] = parser_cls

        for extension in parser_cls.extensions:
            assert extension not in PARSERS_BY_EXTENSION, extension
            PARSERS_BY_EXTENSION[extension] = parser_cls

        for mime_type in parser_cls.mime_types:
            assert mime_type not in PARSERS_BY_MIME_TYPE
            PARSERS_BY_MIME_TYPE[mime_type] = parser_cls


LIBRARY_EXT = 'dll' if sys.platform == 'win32' else 'so'

TREE_SITTER_DIR = os.path.normpath(os.environ.get('TREE_SITTER_DIR', os.path.expanduser('~/.tree-sitter')))
TREE_SITTER_REPOS_DIR = os.path.join(TREE_SITTER_DIR, 'repos')
TREE_SITTER_BUILD_DIR = os.path.join(TREE_SITTER_DIR, 'build')
TREE_SITTER_LIBRARY = os.path.join(TREE_SITTER_BUILD_DIR, f'my-languages.{LIBRARY_EXT}')
TREE_SITTER_LANGUAGES = os.path.join(TREE_SITTER_BUILD_DIR, 'languages.json')

os.makedirs(TREE_SITTER_REPOS_DIR, exist_ok=True)
os.makedirs(TREE_SITTER_BUILD_DIR, exist_ok=True)


def build_tree_sitter_library():
    languages = sorted(
        (parser_cls.tree_sitter_language_name, parser_cls.tree_sitter_subdir)
        for parser_cls in PARSERS
        if parser_cls.tree_sitter_language_name and parser_cls.name != 'PythonNotebook'
    )
    assert len(set(languages)) == len(languages), 'More than one class is using the same tree-sitter language'

    languages_json = json.dumps(languages, indent=2)
    if os.path.isfile(TREE_SITTER_LANGUAGES):
        with open(TREE_SITTER_LANGUAGES, 'rt') as f:
            built_languages_json = f.read()
        if built_languages_json == languages_json:
            return

    shutil.rmtree(TREE_SITTER_BUILD_DIR)
    os.mkdir(TREE_SITTER_BUILD_DIR)

    repo_dirs = [os.path.join(TREE_SITTER_REPOS_DIR, f'tree-sitter-{name}', *subdir) for name, subdir in languages]
    Language.build_library(TREE_SITTER_LIBRARY, repo_dirs)

    with open(TREE_SITTER_LANGUAGES, 'wt') as f:
        f.write(languages_json)


def set_tree_sitter_languages():
    for parser_cls in PARSERS:
        if parser_cls.tree_sitter_language_name:
            parser_cls.tree_sitter_language = Language(TREE_SITTER_LIBRARY, parser_cls.tree_sitter_language_name)


MAGIC = Magic(mime=True)


def detect_mime(body: bytes) -> str:
    try:
        return MAGIC.from_buffer(body)
    except MagicException:
        return ''


def detect(path: str, mime_type: Optional[str] = None) -> Optional[Type[BaseParser]]:
    parser_cls = None

    if '.' in path:
        extension = path.rsplit('.', 1)[-1].lower()
        parser_cls = PARSERS_BY_EXTENSION.get(extension)

    if parser_cls is None and mime_type is not None:
        parser_cls = PARSERS_BY_MIME_TYPE.get(mime_type)

    return parser_cls
