import difflib
import os
import re
from typing import Iterable


def get_next_free_numbered_file(issue_log_dir: str) -> int:
    highest = -1
    for name in os.listdir(issue_log_dir):
        name = name.split('.')[0]
        if name and name.isdigit():
            highest = max(highest, int(name))
    return highest + 1


def split_to_lines_and_clean(text: str) -> list[str]:
    return [line for line in (line.rstrip() for line in text.splitlines()) if line]


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


def read_text_files(paths: list[str], encoding='utf-8-sig') -> Iterable[str]:
    for path in paths:
        yield read_text_file(path, encoding)


def iter_tree(basedir: str) -> Iterable[str]:
    for dirpath, _, filenames in os.walk(basedir):
        for filename in filenames:
            yield os.path.join(dirpath, filename)


def keep_lines(text: str, rx: re.Pattern, separator='\n') -> str:
    return '\n'.join(line for line in text.split(separator) if rx.match(line) is not None)


def remove_lines(text: str, rx: re.Pattern, separator='\n') -> str:
    return '\n'.join(line for line in text.split(separator) if rx.match(line) is None)
