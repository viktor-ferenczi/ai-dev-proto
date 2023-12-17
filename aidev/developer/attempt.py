from pydantic import BaseModel

from ..common.config import C
from ..common.util import count_changed_lines
from ..engine.params import GenerationParams
from ..sonar.issue import Issue, SimpleEnum


class AttemptState(SimpleEnum):
    GENERATED = 'GENERATED'
    INVALID = 'INVALID'
    BUILD_FAILED = 'BUILD_FAILED'
    TEST_FAILED = 'TEST_FAILED'
    SUCCESSFUL = 'SUCCESSFUL'


class Attempt(BaseModel):
    state: AttemptState
    error: str
    path: str
    issue: Issue
    original: str
    system: str
    instruction: str
    params: GenerationParams
    completion: str
    replacement: str

    # Runtime data
    log_path: str = ''
    modified_lines: int = -1

    def count_modified_lines(self) -> int:
        if self.modified_lines < 0:
            self.modified_lines = count_changed_lines(self.original, self.replacement)
        return self.modified_lines

    def write_log(self):
        assert self.log_path, 'No log_path set yet'
        with open(self.log_path, 'wt', encoding='utf-8') as f:
            f.write(self.to_markdown())

    def to_markdown(self) -> str:
        doctype = C.DOCTYPE_BY_EXTENSION.get(self.path.rsplit('.', 1)[-1].lower(), '')
        return f'''\
# STATE
`{self.state}`

# ERROR
{self.error or 'OK'}

# PATH
`{self.path}`

# ISSUE
```json
{self.issue.model_dump_json(indent=2)}
```

# ORIGINAL
```{doctype}
{self.original}
```

# SYSTEM
{self.system}

# INSTRUCTION
{self.instruction}

# PARAMS
```json
{self.params.model_dump_json(indent=2)}
```

# COMPLETION
{self.completion}

# REPLACEMENT
```{doctype}
{self.replacement}
```
'''
