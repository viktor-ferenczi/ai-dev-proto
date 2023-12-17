import os


class C:
    # LLM model name: codellama, deepseek
    # It is used to select the right tokenizer and chat template
    AIDEV_MODEL = os.getenv('AIDEV_MODEL', 'deepseek')

    # OpenAI API compatible LLM engine
    AIDEV_OPENAI_BASE_URL = os.getenv('AIDEV_OPENAI_BASE_URL', 'http://127.0.0.1:8000/v1')
    AIDEV_OPENAI_KEY = os.getenv('AIDEV_OPENAI_KEY', 'NO-KEY')
    AIDEV_OPENAI_MODEL = os.getenv('AIDEV_OPENAI_MODEL', 'model')

    # vLLM API
    AIDEV_VLLM_BASE_URL = os.getenv('AIDEV_VLLM_BASE_URL', 'http://127.0.0.1:8000/v1')

    # SonarQube API
    SONAR_BASE_URL = os.getenv('SONAR_BASE_URL', 'http://127.0.0.1:9000')
    SONAR_TOKEN: str = os.getenv('SONAR_TOKEN', '')

    # Markdown code block type by file extension
    DOCTYPE_BY_EXTENSION = {
        'cs': 'cs',
        'py': 'python',
        'cshtml': 'cshtml',
    }

    # Top of source marker by file extension
    TOP_MARKER_BY_EXTENSION = {
        'cs': '// TOP_MARKER',
        'py': '# TOP_MARKER',
        'cshtml': '<!-- TOP_MARKER -->',
    }
