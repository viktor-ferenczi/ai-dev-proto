from hashlib import sha1
from typing import Optional, Dict, Iterable, Tuple, TypeAlias, Set

from pydantic import BaseModel

from aidev.common.config import C
from aidev.common.util import SimpleEnum
from aidev.editing.model import Block

Identifier: TypeAlias = str


class Category(SimpleEnum):
    # Programming language specific, down to the statement level.
    # Relations express the variable level references from assignments and expressions.

    SOURCE = 'SOURCE'
    """Entire source file, global level"""

    NAMESPACE = 'NAMESPACE'
    """Namespace declaration"""

    USING = 'USING'
    """Using a namespace (import)"""

    TYPE_ALIAS = 'TYPE_ALIAS'
    """Type alias"""

    INTERFACE = 'INTERFACE'
    """Interface declaration (global, namespace or inner)"""

    CLASS = 'CLASS'
    """Class declaration (global, namespace or inner)"""

    STRUCT = 'STRUCT'
    """Struct declaration (global, namespace or inner)"""

    RECORD = 'RECORD'
    """Record declaration (global, namespace or inner)"""

    FUNCTION = 'FUNCTION'
    """Function (global, inner) or method (interface, class, struct) declaration"""

    # Do we need it?
    LAMBDA = 'LAMBDA'
    """Function in an expression without a name"""

    VARIABLE = 'VARIABLE'
    """Variable (global, member, class, local)"""

    STATEMENT = 'STATEMENT'
    """Statement (global or inside a function)"""

    # Text
    PARAGRAPH = 'PARAGRAPH'
    MENTION = 'MENTION'

    # Markdown
    # TODO


class Relation(SimpleEnum):
    CHILD = 'CHILD'
    PARENT = 'PARENT'
    USES = 'USES'
    USED_BY = 'USED_BY'


OPPOSITE_RELATIONS = {
    Relation.CHILD: Relation.PARENT,
    Relation.PARENT: Relation.CHILD,
    Relation.USES: Relation.USED_BY,
    Relation.USED_BY: Relation.USES,
}


class Symbol(BaseModel):
    """Code map graph node, represents a programming language or document format specific construct
    """
    id: Identifier
    """Globally unique identifier in the solution"""

    path: str
    """Solution relative path of the source file"""

    category: Category
    """Category of the symbol"""

    block: Optional[Block] = None
    """Block of lines which contain the entire definition"""

    name: Optional[str] = None
    """Name of the symbol without the namespace, the namespace is connected via a relation"""

    def __hash__(self) -> int:
        return hash(self.id)

    @classmethod
    def new(cls, path: str, category: Category, block: Optional[Block], name: Optional[str] = None) -> 'Symbol':
        block_signature = '' if block is None else f'#{block.begin}:{block.end}'
        id = f'{path}{block_signature}|{category}|{name or ""}'
        if C.HASH_SYMBOL_IDS:
            id = sha1(id.encode('utf-8')).hexdigest()
        return cls(
            id=id,
            path=path,
            category=category,
            block=block,
            name=name,
        )


class Graph(BaseModel):
    """The code map is a directed graph of symbols and their relations

    The code map may contain cycles, should a circular dependency exists
    in the source code. Any recursive iteration must keep track of visited
    symbols and handle cycles in finite time.

    """
    symbols: Dict[Identifier, Symbol]
    relations: Dict[Identifier, Dict[Identifier, Relation]]

    @classmethod
    def new(cls) -> 'Graph':
        return cls(symbols={}, relations={})

    def __ior__(self, other: 'Graph'):
        assert isinstance(other, Graph)

        self.symbols.update(other.symbols)

        for id, other_relations in other.relations.items():
            this_relations = self.relations.get(id)
            if this_relations is None:
                self.relations[id] = this_relations = {}
            this_relations.update(other_relations)

    def add_symbol(self, symbol: Symbol):
        self.symbols[symbol.id] = symbol

    def add_relation(self, existing: Symbol, relation: Relation, new: Symbol):
        assert existing.id in self.symbols, 'Symbol A is not registered'
        assert new.id in self.symbols, 'Symbol B is not registered'
        relations = self.relations.get(existing.id)
        if relations is None:
            self.relations[existing.id] = relations = {}
        relations[new.id] = relation

    def add_relation_both_ways(self, existing: Symbol, relation: Relation, new: Symbol):
        opposite = OPPOSITE_RELATIONS[relation]
        self.add_relation(existing, relation, new)
        self.add_relation(new, opposite, existing)

    def add_symbol_and_relation(self, existing: Symbol, relation: Relation, new: Symbol):
        self.add_symbol(new)
        self.add_relation(existing, relation, new)

    def add_symbol_and_relation_both_ways(self, existing: Symbol, relation: Relation, new: Symbol):
        self.add_symbol(new)
        self.add_relation_both_ways(existing, relation, new)

    def iter_related(self, symbol: Symbol) -> Iterable[Tuple[Relation, Symbol]]:
        relations: Dict[Identifier, Relation] = self.relations.get(symbol.id)
        if relations is not None:
            for id, relation in relations.items():
                yield relation, self.symbols[id]

    def walk_related(self, first_symbol: Symbol, follow_relation: Relation) -> Iterable[Symbol]:
        visited: Set[Identifier] = set()

        stack = [first_symbol]
        while stack:
            symbol = stack.pop()
            visited.add(symbol.id)

            relations: Dict[Identifier, Relation] = self.relations.get(symbol.id)
            if relations is None:
                continue

            for id, relation in relations.items():
                if relation == follow_relation and id not in visited:
                    symbol = self.symbols[id]
                    yield symbol
                    stack.append(symbol)
