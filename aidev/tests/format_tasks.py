import json
import os

from aidev.common.config import C
from aidev.common.util import render_markdown_template
from aidev.workflow.model import Task

SCRIPT_DIR = os.path.normpath(os.path.dirname(__file__))
TASKS_DIR = os.path.join(SCRIPT_DIR, 'tasks')


def test():
    tasks_dir = r'C:\Dev\AI\Coding\example-shop\.aidev\tasks'
    for fn in os.listdir(tasks_dir):
        if not fn.endswith('.json'):
            continue
        fp = os.path.join(tasks_dir, fn)
        with open(fp, 'rt', encoding='utf-8-sig') as f:
            task = Task(**json.load(f))
        md = render_markdown_template('task', task=task)
        md_path = os.path.join(TASKS_DIR, fn[:-5] + '.md')
        with open(md_path, 'wt', encoding='utf-8-sig') as f:
            f.write(md)


if __name__ == '__main__':
    test()
