import difflib
import os


def get_next_free_numbered_dir(issue_log_dir: str) -> int:
    highest = -1
    for name in os.listdir(issue_log_dir):
        if name.isdigit():
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
