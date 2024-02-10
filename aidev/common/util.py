import asyncio
import hashlib
import difflib
import os
import re
import time
import uuid
import shutil
from contextlib import contextmanager
from enum import Enum
from logging import Logger, INFO, getLogger, StreamHandler, Formatter
from typing import Iterable, List, Callable, Iterator, Awaitable, Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, Template

from .config import C


# Reduce the warnings about long-running tasks
def set_slow_callback_duration_threshold(duration: float):
    asyncio.get_running_loop().slow_callback_duration = duration


def get_next_free_numbered_file(issue_log_dir: str) -> int:
    highest = -1
    for name in os.listdir(issue_log_dir):
        name = name.split('.')[0]
        if name and name.isdigit():
            highest = max(highest, int(name))
    return highest + 1


def split_to_lines_and_clean(text: str) -> List[str]:
    return [line for line in (line.rstrip() for line in text.splitlines()) if line]


def join_lines(lines: Iterable[str]) -> str:
    return '\n'.join(lines)


def join_lines_lf(lines: Iterable[str]) -> str:
    return ''.join(f'{line}\n' for line in lines)


def replace_tripple_backquote(text: str) -> str:
    return text.replace('```', r'\`\`\`')


def count_changed_lines(original: str, replacement: str) -> int:
    """
    Counts the number of lines changed, added, or removed between the original and replacement strings.

    Args:
    original (str): The original string.
    replacement (str): The replacement string.

    Returns:
    int: The number of lines changed, added, or removed.
    """
    # Split the strings into lines and remove empty lines and trailing whitespace
    original_lines = split_to_lines_and_clean(original)
    replacement_lines = split_to_lines_and_clean(replacement)

    # Create a Differ object and calculate the differences
    differ = difflib.Differ()

    # Count the number of lines that are added (+), removed (-), or changed (?)
    change_count = sum((1 for line in differ.compare(original_lines, replacement_lines) if line.startswith(('+', '-', '?'))), 0)
    return change_count


assert count_changed_lines("\n\n\nline 1\nline 2\n\nline 3\nline 4", "line 1\nline 2 changed\nline 3\nnew line 5") == 4


def write_binary_file(path: str, data: bytes):
    with open(path, 'rb') as f:
        f.write(data)


def read_binary_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def write_text_file(path: str, content: str, encoding='utf-8'):
    with open(path, 'wt', encoding=encoding) as f:
        f.write(content)


def read_text_file_or_default(path: str, default: str, encoding='utf-8-sig') -> str:
    if not os.path.exists(path):
        return default

    with open(path, 'rt', encoding=encoding) as f:
        return f.read()


def read_text_file(path: str, encoding='utf-8-sig') -> str:
    with open(path, 'rt', encoding=encoding) as f:
        return f.read()


def read_text_files(paths: List[str], encoding='utf-8-sig') -> Iterable[str]:
    for path in paths:
        yield read_text_file(path, encoding)


def iter_tree(basedir: str) -> Iterable[str]:
    for dirpath, _, filenames in os.walk(basedir):
        for filename in filenames:
            yield os.path.join(dirpath, filename)


def keep_lines(text: str, rx: re.Pattern, separator='\n') -> str:
    return join_lines(line for line in text.split(separator) if rx.match(line) is not None)


def remove_lines(text: str, rx: re.Pattern, separator='\n') -> str:
    return join_lines(line for line in text.split(separator) if rx.match(line) is None)


def extract_code_from_completion(completion: str) -> (str, str):
    i = completion.find('```')
    j = completion.rfind('```')

    if i < 0 or j <= i:
        return '', 'Missing code block'

    i = completion.find('\n', i) + 1
    if i <= 0:
        return '', 'Missing newline after start of code block'

    code = completion[i:j].lstrip()
    if not code.strip():
        return 'Empty code', ''

    return code, ''


def copy_indent(example: str, text: str) -> str:
    return example[:-len(example.lstrip())] + text.lstrip()


class SimpleEnum(str, Enum):

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return f"{self.__class__.__name__}.{self.name}"


def get_prompt_template_for_model(model: str) -> Template:
    prompt_template_name = C.PROMPT_TEMPLATES[model]
    source = read_text_file(os.path.join(C.PROMPT_TEMPLATES_DIR, f'{prompt_template_name}.jinja'))
    environment = Environment()
    prompt_template = environment.from_string(source)
    return prompt_template


def extract_code_blocks(completion: str) -> List[str]:
    parts = ('\n' + completion).split('\n```')
    if len(parts) < 2:
        return []

    return [
        parts[i].split('\n', 1)[1]
        for i in range(1, len(parts), 2)
    ]


def init_logger(loglevel=INFO) -> Logger:
    logger = getLogger()
    logger.setLevel(loglevel)

    handler = StreamHandler()
    handler.setLevel(loglevel)

    formatter = Formatter('%(asctime)s %(name)s [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger


def render_template(_path: str, **variables) -> str:
    if not os.path.exists(_path):
        raise FileNotFoundError(f"The file {_path} does not exist.")

    env = Environment(loader=FileSystemLoader(os.path.dirname(_path)))
    template = env.get_template(os.path.basename(_path))
    return template.render(**variables)


def render_workflow_template(_name: str, **variables) -> str:
    path = os.path.join(C.WORKFLOW_TEMPLATES_DIR, f'{_name}.jinja')
    return unindent_code_blocks(render_template(path, **variables))


def render_markdown_template(_name: str, **variables) -> str:
    path = os.path.join(C.MARKDOWN_TEMPLATES_DIR, f'{_name}.jinja')
    return unindent_code_blocks(render_template(path, **variables))


def unindent_code_blocks(md: str) -> str:
    lines = md.split('\n')

    in_code = False
    for i, line in enumerate(lines):

        if line.lstrip().startswith('```'):
            lines[i] = line.strip()
            in_code = not in_code
            continue

        if not in_code:
            lines[i] = line.strip()

    return join_lines(lines)


def regex_from_lines(lines: List[str]) -> str:
    return ''.join(rf'({re.escape(path)}\n)?' for path in lines)


def copy_directory(src: str, dst: str):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def find(lst: List[object], predicate: Callable[[object], bool]):
    for i, v in enumerate(lst):
        if predicate(v):
            return i
    return -1


def find_iter(text: str, sub: str) -> Iterator[int]:
    i = 0
    e = len(text)
    while i < e:
        f = text.find(sub, i)
        if f < 0:
            break
        yield f
        i = f + len(sub)


def new_uuid() -> str:
    return str(uuid.uuid4())


async def sleep_forever():
    while 1:
        await asyncio.sleep(3600)


def retry(fn: Callable[[], Any], handle_exceptions=(), max_retries: int = 9, delay: float = 0.01, delay_multiplier: float = 1.4142135, max_delay: float = 1.0) -> Any:
    for attempt in range(max_retries):
        try:
            return fn()
        except handle_exceptions:
            time.sleep(delay)
            delay = min(max_delay, delay * delay_multiplier)

    return fn()


async def async_retry(fn: Callable[[], Awaitable[Any]], handle_exceptions=(), max_retries: int = 9, delay: float = 0.01, delay_multiplier: float = 1.4142135, max_delay: float = 1.0) -> Any:
    for attempt in range(max_retries):
        try:
            return await fn()
        except handle_exceptions as e:
            print(f'WARNING: Retry {1 + attempt}/{max_retries} of {fn.__name__} in {delay:.3f}s due to error: [{e.__class__.__name__}] {e}')
            await asyncio.sleep(delay)
            delay = min(max_delay, delay * delay_multiplier)

    return await fn()


def hash_bytes(data: bytes) -> str:
    sha = hashlib.sha256()
    sha.update(data)
    return sha.hexdigest()


def hash_file(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        while 1:
            chunk = f.read(0x8000)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def count_lines(text: str) -> int:
    return 1 + text.count('\n')


def decode_normalize(content: bytes) -> str:
    try:
        decoded = content.decode('utf-8')
    except UnicodeDecodeError:
        decoded = content.decode('latin-1')

    return normalize(decoded)


def normalize(content: str) -> str:
    return content.replace('\r\n', '\n').replace('\r', '').replace('\0', '\f')


@contextmanager
def timer(prefix='', *, count: int = None, unit: str = None, stats: Dict[str, any] = None, minimum: Optional[float] = None, show: bool = True):
    started = time.time()
    yield
    duration = time.time() - started

    frequency = None
    frequency_text = ''
    if count and isinstance(count, int):
        frequency = count / max(1e-6, duration)
        frequency_text = f' ({frequency:.1f}{" " + unit if unit else ""}/s)'

    if stats is not None:
        stats['duration'] = duration
        if count is not None:
            stats['count'] = count
        if unit is not None:
            stats['unit'] = unit
        if frequency is not None:
            stats['frequency'] = frequency

    if show and (minimum is None or duration >= minimum):
        print(f'{prefix} in {duration:.3f}s{frequency_text}')
