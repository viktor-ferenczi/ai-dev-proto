from pydantic import BaseModel
from typing import List
from datetime import datetime

from enum import Enum

UNKNOWN_DATETIME = datetime.utcfromtimestamp(0)


class SimpleEnum(Enum):

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return f"{self.__class__.__name__}.{self.name}"


class BooleanChoice(SimpleEnum):
    TRUE = "true"
    FALSE = "false"
    YES = "yes"
    NO = "no"

    def __bool__(self) -> bool:
        return self.value in (BooleanChoice.TRUE, BooleanChoice.YES)


# See https://docs.sonarsource.com/sonarqube/latest/user-guide/clean-code/
class CleanCodeAttribute(SimpleEnum):
    UNKNOWN = "UNKNOWN"
    FORMATTED = "FORMATTED"
    CONVENTIONAL = "CONVENTIONAL"
    IDENTIFIABLE = "IDENTIFIABLE"
    CLEAR = "CLEAR"
    LOGICAL = "LOGICAL"
    COMPLETE = "COMPLETE"
    EFFICIENT = "EFFICIENT"
    FOCUSED = "FOCUSED"
    DISTINCT = "DISTINCT"
    MODULAR = "MODULAR"
    TESTED = "TESTED"
    LAWFUL = "LAWFUL"
    TRUSTWORTHY = "TRUSTWORTHY"
    RESPECTFUL = "RESPECTFUL"


CLEAN_CODE_ATTRIBUTE_DESCRIPTIONS = {
    CleanCodeAttribute.UNKNOWN: "N/A",
    CleanCodeAttribute.FORMATTED: "The code presentation is systematic and regular. Non-semantic choices, such as spacing, indentation, and character placement, remain consistent throughout the codebase, maintaining uniformity across files and authors.",
    CleanCodeAttribute.CONVENTIONAL: "The code performs tasks with expected instructions. Faced with equally good options, the code adheres to a single choice across all instances, preferring language conventions. This includes using the appropriate programming interfaces and language features.",
    CleanCodeAttribute.IDENTIFIABLE: "The names follow a regular structure based on language conventions. The casing, word separators, suffixes, and prefixes used in the identifiers have purpose, without arbitrary differences.",
    CleanCodeAttribute.CLEAR: "The code is self-explanatory, transparently communicating its functionality. It is written in a straightforward way that minimizes ambiguity, avoiding unnecessary clever or intricate solutions.",
    CleanCodeAttribute.LOGICAL: "The code has well-formed and sound instructions that work together. It is free of explicit errors, contradictions, and commands that could be unpredictable or objectionable.",
    CleanCodeAttribute.COMPLETE: "The code constructs are comprehensive, used adequately and thoroughly. The code is functional and achieves its implied goals. There are no obviously incomplete or lacking solutions.",
    CleanCodeAttribute.EFFICIENT: "The code utilizes resources without needless waste. It prioritizes economical options when available, avoiding unnecessary consumption of memory, processor, disk, or network resources.",
    CleanCodeAttribute.FOCUSED: "The code has a single, narrow, and specific scope. Each unit should have only one concise purpose, without an overwhelming accumulation of instructions or excessive amounts of complexity.",
    CleanCodeAttribute.DISTINCT: "The code procedures and data are unique and distinctive, without undue duplication. The codebase has no significant repetition where it could be decomposed into smaller shared segments.",
    CleanCodeAttribute.MODULAR: "The code has been organized and distributed to emphasize the separation between its parts. The relationships within the code are carefully managed, ensuring they are minimal and clearly defined.",
    CleanCodeAttribute.TESTED: "The code has automated checks that provide confidence in the functionality. It has enough test coverage which enables changes in implementation without the risk of functional regressions.",
    CleanCodeAttribute.LAWFUL: "The code respects licensing and copyright regulation. It exercises the creator’s rights and honors other’s rights to license their own code.",
    CleanCodeAttribute.TRUSTWORTHY: "The code abstains from revealing or hard-coding private information. It preserves sensitive private information such as credentials and personally-identifying information.",
    CleanCodeAttribute.RESPECTFUL: "The code refrains from using discriminatory and offensive language. It chooses to prioritize inclusive terminology whenever an alternative exists that conveys the same meaning.",
}


class CleanCodeAttributeCategory(SimpleEnum):
    UNKNOWN = "UNKNOWN"
    ADAPTABLE = 'ADAPTABLE'
    CONSISTENT = 'CONSISTENT'
    INTENTIONAL = 'INTENTIONAL'
    RESPONSIBLE = 'RESPONSIBLE'


class ImpactSeverity(SimpleEnum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ImpactSoftwareQuality(SimpleEnum):
    UNKNOWN = "UNKNOWN"
    MAINTAINABILITY = "MAINTAINABILITY"
    RELIABILITY = "RELIABILITY"
    SECURITY = "SECURITY"


class IssueStatus(SimpleEnum):
    UNKNOWN = "UNKNOWN"
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    ACCEPTED = "ACCEPTED"
    FIXED = "FIXED"
    CLOSED = "CLOSED"


class IssueScope(SimpleEnum):
    UNKNOWN = "UNKNOWN"
    MAIN = "MAIN"
    TEST = "TEST"


class IssueType(SimpleEnum):
    UNKNOWN = "UNKNOWN"
    CODE_SMELL = "CODE_SMELL"
    BUG = "BUG"
    VULNERABILITY = "VULNERABILITY"


class IssueSeverity(SimpleEnum):
    UNKNOWN = "UNKNOWN"
    CRITICAL = 'CRITICAL'
    HIGH = 'HIGH'
    MAJOR = 'MAJOR'
    MINOR = 'MINOR'
    INFO = 'INFO'


# noinspection PyPep8Naming
class Impact(BaseModel):
    severity: ImpactSeverity = ImpactSeverity.UNKNOWN
    softwareQuality: ImpactSoftwareQuality = ImpactSoftwareQuality.UNKNOWN


# noinspection PyPep8Naming
class TextRange(BaseModel):
    endLine: int = 0
    endOffset: int = 0
    startLine: int = 0
    startOffset: int = 0


class MessageFormatting(BaseModel):
    start: int = 0
    end: int = 0
    type: str = 'UNKNOWN'  # FIXME: Should be an Enum, but the only known example is 'CODE'


# noinspection PyPep8Naming
class FlowLocation(BaseModel):
    component: str = ''
    textRange: TextRange = TextRange()
    msgFormattings: List[MessageFormatting] = []


class Flow(BaseModel):
    locations: List[FlowLocation] = []


# noinspection PyPep8Naming
class Issue(BaseModel):
    author: str = ''
    cleanCodeAttribute: CleanCodeAttribute = CleanCodeAttribute.UNKNOWN
    cleanCodeAttributeCategory: CleanCodeAttributeCategory = CleanCodeAttributeCategory.UNKNOWN
    codeVariants: List[str] = []  # 'windows', 'linux', ...
    component: str = ''
    creationDate: datetime = datetime.now()
    debt: str = ''
    effort: str = ''
    flows: List[Flow] = []
    hash: str = ''
    impacts: List[Impact] = []
    key: str = ''
    line: int = 0
    message: str = ''
    messageFormattings: List[MessageFormatting] = []
    project: str = ''
    quickFixAvailable: bool = False
    rule: str = ''
    scope: IssueScope = IssueScope.UNKNOWN
    severity: IssueSeverity = IssueSeverity.UNKNOWN
    status: IssueStatus = IssueStatus.UNKNOWN
    tags: List[str] = []
    textRange: TextRange = TextRange()
    type: IssueType = IssueType.UNKNOWN
    updateDate: datetime = UNKNOWN_DATETIME

    @property
    def sourceRelPath(self) -> str:
        return self.component.split(':', 1)[1]
