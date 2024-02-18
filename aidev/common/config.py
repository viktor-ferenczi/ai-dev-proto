import os
from typing import Dict, Iterable

import toml

AIDEV_PACKAGE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))


class Config:
    # Common flags
    VERBOSE = False

    # Project (solution)
    PROJECT_DIR: str = os.getenv('AIDEV_PROJECT_DIR', '')
    PROJECT_NAME: str = os.getenv('AIDEV_PROJECT_DIR', '')
    PROJECT_BRANCH: str = os.getenv('AIDEV_PROJECT_BRANCH', '')

    # LLM model name (valid values are the keys of Config._MODEL_NAMES)
    # It is used to select the right tokenizer, chat template, max context size and optimal parallel sequence count
    MODEL: str = os.getenv('AIDEV_MODEL', 'deepseek-coder')

    # Engine selection: 'openai' or 'vllm'
    ENGINE: str = 'vllm'

    # OpenAI API compatible LLM engine
    OPENAI_BASE_URL: str = os.getenv('AIDEV_OPENAI_BASE_URL', 'http://127.0.0.1:8000/v1')
    OPENAI_KEY: str = os.getenv('AIDEV_OPENAI_KEY', 'NO-KEY')
    OPENAI_MODEL: str = os.getenv('AIDEV_OPENAI_MODEL', 'model')

    # vLLM API
    VLLM_BASE_URL: str = os.getenv('AIDEV_VLLM_BASE_URL', 'http://127.0.0.1:8000')

    # SonarQube API
    SONAR_BASE_URL: str = os.getenv('SONAR_BASE_URL', 'http://127.0.0.1:9000')
    SONAR_TOKEN: str = os.getenv('SONAR_TOKEN', '')

    # Coding
    KEEP_FAILING_CODE: bool = os.getenv('AIDEV_KEEP_FAILING_CODE', 'n').lower() in ('1', 'y', 'yes', 't', 'true')

    # Task orchestration
    MAX_PARALLEL_TASKS: int = 1

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

    # Valid models
    MODEL_NAMES: Dict[str, str] = {
        'codellama': 'CodeLlama',
        'deepseek-coder': 'DeepSeek Coder',
        'deepseek-llm': 'DeepSeek LLM',
        'yi': 'Yi',
    }

    # Maximum context size of models
    CONTEXT_SIZE: Dict[str, int] = {
        'codellama': 16384,  # Should work at 32k or even 64k, but it needs changes in engine config
        'deepseek-coder': 16384,
        'deepseek-llm': 4096,
        'yi': 65536,
    }

    # Optimal parallel sequence counts of models
    OPTIMAL_PARALLEL_SEQUENCES: Dict[str, int] = {
        'codellama': 16,
        'deepseek-coder': 16,
        'deepseek-llm': 16,
        'yi': 16,
    }

    # Directory with the Jinja2 prompt templates
    TEMPLATES_DIR = os.path.join(AIDEV_PACKAGE_DIR, 'templates')
    PROMPT_TEMPLATES_DIR = os.path.join(TEMPLATES_DIR, 'prompt')
    WORKFLOW_TEMPLATES_DIR = os.path.join(TEMPLATES_DIR, 'workflow')
    MARKDOWN_TEMPLATES_DIR = os.path.join(TEMPLATES_DIR, 'markdown')

    # Prompt templates for each model
    PROMPT_TEMPLATES = {
        'codellama': 'llama-2-chat',
        'deepseek-coder': 'deepseek-coder',
        'deepseek-llm': 'deepseek-llm',
        'yi': 'orca',
    }

    # Async
    SLOW_CALLBACK_DURATION_THRESHOLD = 1.0  # s

    # Code map
    HASH_SYMBOL_IDS = False

    # Planning
    MAX_PLANNING_STEPS = 10

    # Prompts
    SYSTEM_CODING_ASSISTANT = 'You are a helpful coding assistant experienced in C#, .NET Core, HTML, JavaScript and Python.'

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
