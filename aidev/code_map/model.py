from collections import defaultdict
from hashlib import sha1
from typing import Optional, Dict, Iterable, Tuple, TypeAlias, Set, Any, List

from pydantic import BaseModel

from aidev.common.config import C
from aidev.common.util import SimpleEnum
from aidev.editing.model import Block

Identifier: TypeAlias = str


class Category(SimpleEnum):
    """High level category of a named symbol in source code or document section"""
    SOURCE = 'SOURCE'
    """One specific source file (top level, always present)"""

    BLOCK = 'BLOCK'
    """Named, but untyped document block (section, CSS style, HTML element)"""

    IMPORT = 'IMPORT'
    """Importing or including a specific source file"""

    NAMESPACE = 'NAMESPACE'
    """Namespace"""

    USING = 'USING'
    """Using a namespace"""

    TYPE = 'TYPE'
    """Type, type alias, interface, trait, class, struct, record"""

    FUNCTION = 'FUNCTION'
    """Function (global, inner) or method (interface, trait, class, struct) declaration, including propery get/set"""

    VARIABLE = 'VARIABLE'
    """Variable (global, class, struct, member, local)"""


NAMESPACE_AWARE_CATEGORIES = (
    Category.USING,
    Category.TYPE,
    Category.FUNCTION,
    Category.VARIABLE,
)


class Reference(BaseModel):
    """ Reference collected while parsing the source code
    """
    name: str
    category: Category

    @classmethod
    def new(cls, name: str, category: Category):
        return cls(name=name, category=category)

    def __hash__(self) -> int:
        return hash(self.name) ^ hash(self.category)


class Symbol(BaseModel):
    """Code map graph node, represents a programming language or document format specific construct
    """
    parent: Optional[Identifier]
    """ID of the parent, source files don't have a parent"""

    category: Category
    """Category of the symbol"""

    name: str
    """Name of the symbol without the namespace, solution relative path for source"""

    block: Block
    """Block of lines which contain the entire definition"""

    children: Set[Identifier]
    """IDs of the symbols directly under this one"""

    dependencies: Set[Identifier]
    """IDs of the symbols this symbol uses, inverse of dependents"""

    dependents: Set[Identifier]
    """IDs of the symbols using this one, inverse of dependencies"""

    references: Optional[Set[Reference]] = None
    """Reference collected while parsing the source code, they are turned into proper dependencies by cross-referencing"""

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Symbol) and self.id == other.id

    def __ne__(self, other: Any) -> bool:
        return isinstance(other, Symbol) and self.id != other.id

    @property
    def id(self) -> str:
        id = f'{self.category}|{self.name}|{self.block.begin}:{self.block.end}'
        if C.HASH_SYMBOL_IDS:
            id = sha1(id.encode('utf-8')).hexdigest()
        return id

    @classmethod
    def new(cls, parent: Optional['Symbol'], category: Category, name: str, block: Block) -> 'Symbol':
        if parent is None:
            parent_id = None
        else:
            assert isinstance(parent, Symbol)
            parent_id = parent.id

        symbol = cls(
            parent=parent_id,
            category=category,
            name=name,
            block=block,
            children=set(),
            dependencies=set(),
            dependents=set(),
            references=set(),
        )

        if parent is not None:
            parent.children.add(symbol.id)

        return symbol

    def uses(self, symbol: 'Symbol'):
        assert isinstance(symbol, Symbol)
        self.dependencies.add(symbol.id)
        symbol.dependents.add(self.id)

    def used_by(self, symbol: 'Symbol'):
        assert isinstance(symbol, Symbol)
        self.dependents.add(symbol.id)
        symbol.dependencies.add(self.id)


NamespaceSymbolMap: TypeAlias = Dict[str, Dict[str, List[Symbol]]]


class Graph(BaseModel):
    """The code map is a directed graph of symbols and their relations

    The code map may contain cycles, should a circular dependency exists
    in the source code. Any recursive iteration must keep track of visited
    symbols and handle cycles in finite time.

    """
    symbols: Dict[Identifier, Symbol]

    @classmethod
    def new(cls) -> 'Graph':
        return cls(symbols={})

    def update(self, other: 'Graph'):
        assert isinstance(other, Graph)

        conflicts: Set[Identifier] = set(self.symbols) & set(other.symbols)
        if conflicts:
            raise ValueError(f'Conflicting symbols: {sorted(conflicts)!r}')

        self.symbols.update(other.symbols)

    def new_source(self, path: str, file_line_count: int):
        symbol: Symbol = Symbol.new(None, Category.SOURCE, path, Block.from_range(0, file_line_count))
        self.symbols[symbol.id] = symbol
        return symbol

    def new_symbol(self, parent: Symbol, category: Category, name: str, block: Block) -> Symbol:
        symbol: Symbol = Symbol.new(parent, category, name, block)
        self.symbols[symbol.id] = symbol
        return symbol

    def __getitem__(self, id: str) -> Symbol:
        return self.symbols[id]

    def get(self, id: str, default: Optional[Symbol] = None):
        return self.symbols.get(id, default)

    def list(self, ids: Iterable[str]) -> List[Symbol]:
        return [self.symbols[id] for id in ids]

    def iter(self, ids: Iterable[str]) -> Iterable[Symbol]:
        for id in ids:
            yield self.symbols[id]

    def get_parent(self, symbol: Symbol) -> Optional[Symbol]:
        if symbol.parent is None:
            return None
        return self.symbols[symbol.parent]

    def find_parent(self, symbol: Optional[Symbol], category: Category) -> Optional[Symbol]:
        while symbol is not None:
            if symbol.category == category:
                return symbol
            symbol = self.symbols[symbol.parent]

        return None

    def iter_children_of_category(self, symbol: Symbol, category: Category) -> Iterable[Symbol]:
        for child in self.iter(id for id in symbol.children):
            if child.category == category:
                yield child

    def iter_symbols_with_category(self, category: Category) -> Iterable[Symbol]:
        for symbol in self.symbols.values():
            if symbol.category == category:
                yield symbol

    def iter_namespaces_by_name(self, names: Set[str]) -> Iterable[Symbol]:
        for symbol in self.symbols.values():
            if symbol.category == Category.NAMESPACE and symbol.name in names:
                yield symbol

    def iter_parents(self, symbol: Symbol) -> Iterable[Symbol]:
        while 1:
            if symbol.parent is None:
                break
            yield symbol
            symbol = self.symbols[symbol.parent]

    def walk_children(self, parent: Symbol, depth: int = 0, visited: Optional[Set[Identifier]] = None) -> Iterable[Tuple[Symbol, int]]:
        if visited is None:
            visited = {parent.id}

        depth += 1

        for id in parent.children:
            if id in visited:
                continue
            child = self.symbols[id]
            yield child, depth
            if child.children:
                yield from self.walk_children(child, depth, visited)

    def walk_dependencies(self, symbol: Symbol, depth: int = 0, visited: Optional[Set[Identifier]] = None) -> Iterable[Tuple[Symbol, int]]:
        if visited is None:
            visited = {symbol.id}

        depth += 1

        for id in symbol.dependencies:
            if id in visited:
                continue
            dependency = self.symbols[id]
            yield dependency, depth
            if dependency.dependencies:
                yield from self.walk_dependencies(dependency, depth, visited)

    def walk_dependants(self, symbol: Symbol, depth: int = 0, visited: Optional[Set[Identifier]] = None) -> Iterable[Tuple[Symbol, int]]:
        if visited is None:
            visited = {symbol.id}

        depth += 1

        for id in symbol.dependents:
            if id in visited:
                continue
            dependency = self.symbols[id]
            yield dependency, depth
            if dependency.dependents:
                yield from self.walk_dependants(dependency, depth, visited)

    def cross_reference(self):
        self.__remove_external_references()
        namespace_symbol_map: NamespaceSymbolMap = self.__map_symbols_to_namespaces()
        self.__reference_symbols(namespace_symbol_map)
        self.__cleanup(namespace_symbol_map)

    def __remove_external_references(self):
        """ Eliminates references to names with no symbol defined in the source code, all of those are external code
        """
        names_defined: Set[str] = {symbol.name for symbol in self.symbols.values()}
        for symbol in self.symbols.values():
            symbol.references = {reference for reference in symbol.references if reference.name in names_defined}

    def __map_symbols_to_namespaces(self) -> NamespaceSymbolMap:
        namespace_symbol_map: NamespaceSymbolMap = {}
        for namespace in self.iter_symbols_with_category(Category.NAMESPACE):
            namespace_symbol_map[namespace.name] = symbol_map = defaultdict(list)
            symbol_map[namespace.name].append(namespace)

        for namespace_name, symbol_map in namespace_symbol_map.items():
            for namespace in symbol_map[namespace_name]:
                if namespace.category != Category.NAMESPACE:
                    continue

                for symbol, depth in self.walk_children(namespace):
                    if symbol.category in NAMESPACE_AWARE_CATEGORIES:
                        symbol_map[symbol.name].append(symbol)

        return namespace_symbol_map

    # FIXME: It is too wide, more like a search by name disregarding the data type and scoping rules
    # FIXME: It could be further optimized
    def __reference_symbols(self, namespace_symbol_map: NamespaceSymbolMap):
        for namespace_name, symbol_map in namespace_symbol_map.items():

            for namespace in symbol_map[namespace_name]:
                if namespace.category != Category.NAMESPACE:
                    continue

                accessible = {namespace_name}
                source = self.find_parent(namespace, Category.SOURCE)
                for using in self.iter_children_of_category(source, Category.USING):
                    if using.name in namespace_symbol_map:
                        accessible.add(using.name)

                for other_namespace_name in accessible:
                    symbol_map = namespace_symbol_map.get(other_namespace_name)
                    if symbol_map is None:
                        continue

                    for symbol, depth in self.walk_children(namespace):
                        for reference in symbol.references:
                            for other in symbol_map.get(reference.name, ()):
                                if other.category == reference.category:
                                    symbol.uses(other)

    def __cleanup(self, namespace_symbol_map: NamespaceSymbolMap):

        delete: Set[Identifier] = set()

        for symbol in self.symbols.values():
            del symbol.references

            if symbol.category == Category.USING and symbol.name not in namespace_symbol_map:
                delete.add(symbol.id)

        for id in delete:
            symbol = self.symbols[id]
            parent = self.get_parent(symbol)
            parent.children.discard(symbol.id)
            del self.symbols[id]
