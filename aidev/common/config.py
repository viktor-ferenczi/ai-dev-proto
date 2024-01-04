import os
from typing import Dict, Iterable

import toml


class Config:
    # Project (solution)
    PROJECT_DIR: str = os.getenv('AIDEV_PROJECT_DIR', '')
    PROJECT_NAME: str = os.getenv('AIDEV_PROJECT_DIR', '')
    PROJECT_BRANCH: str = os.getenv('AIDEV_PROJECT_BRANCH', '')

    # LLM model name: codellama, deepseek
    # It is used to select the right tokenizer and chat template
    MODEL: str = os.getenv('AIDEV_MODEL', 'deepseek')

    # OpenAI API compatible LLM engine
    OPENAI_BASE_URL: str = os.getenv('AIDEV_OPENAI_BASE_URL', 'http://127.0.0.1:8000/v1')
    OPENAI_KEY: str = os.getenv('AIDEV_OPENAI_KEY', 'NO-KEY')
    OPENAI_MODEL: str = os.getenv('AIDEV_OPENAI_MODEL', 'model')

    # vLLM API
    VLLM_BASE_URL: str = os.getenv('AIDEV_VLLM_BASE_URL', 'http://127.0.0.1:8000/v1')

    # SonarQube API
    SONAR_BASE_URL: str = os.getenv('SONAR_BASE_URL', 'http://127.0.0.1:9000')
    SONAR_TOKEN: str = os.getenv('SONAR_TOKEN', '')

    # Coding
    KEEP_FAILING_CODE: bool = os.getenv('AIDEV_KEEP_FAILING_CODE', 'n').lower() in ('1', 'y', 'yes', 't', 'true')

    # Markdown code block type by file extension
    DOCTYPE_BY_EXTENSION: Dict[str, str] = {
        'cs': 'cs',
        'py': 'python',
        'cshtml': 'cshtml',
    }

    # Top of source marker by file extension
    TOP_MARKER_BY_EXTENSION: Dict[str, str] = {
        'cs': '// TOP_MARKER',
        'py': '# TOP_MARKER',
        'cshtml': '<!-- TOP_MARKER -->',
    }

    def save(self, path: str):
        with open(path, 'wt') as f:
            toml.dump({name: getattr(self, name) for name in self}, f)

    def load(self, path: str):
        print(f'Loading config: {path}')

        with open(path, 'rt') as f:
            data = toml.load(f)

        for name in self:
            if name in data:
                setattr(self, name, data[name])

    def __iter__(self) -> Iterable[str]:
        for name in dir(self):
            if not name.startswith('_') and name == name.upper():
                yield name


CONFIG_DIR = os.path.expanduser('~/.aidev')
os.makedirs(CONFIG_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.toml')
DEFAULT_CONFIG_PATH = os.path.join(CONFIG_DIR, 'default.toml')

C = Config()
C.save(DEFAULT_CONFIG_PATH)

if os.path.exists(CONFIG_PATH):
    C.load(CONFIG_PATH)
