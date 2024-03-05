import os
import re
from collections import defaultdict
from hashlib import sha1
from typing import Optional, Dict, Iterable, Tuple, TypeAlias, Set, Any, List

from pydantic import BaseModel

from aidev.common.config import C
from aidev.common.util import SimpleEnum, read_binary_file
from aidev.editing.model import Block, Hunk, Patch, Document
from aidev.workflow.working_copy import WorkingCopy

Identifier: TypeAlias = str

RX_NAMES = re.compile(r'[a-z_][a-z_0-9]*', re.I)


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
    """Type, type alias, enum, interface, trait, class, struct, record"""

    FUNCTION = 'FUNCTION'
    """Function or method declaration"""

    VARIABLE = 'VARIABLE'
    """Variable or property (global, class, struct, member, local)"""


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
    path: str
    """Solution relative path of the source file this symbol is defined in"""

    block: Block
    """Block of lines which contain the entire definition"""

    parent: Optional[Identifier]
    """ID of the parent, source files don't have a parent"""

    category: Category
    """Category of the symbol"""

    name: str
    """Name of the symbol without the namespace, solution relative path for source"""

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
        id = f'{self.path}#{self.block.begin}:{self.block.end}|{self.category}|{self.name}'
        if C.HASH_SYMBOL_IDS:
            id = sha1(id.encode('utf-8')).hexdigest()
        return id

    @classmethod
    def new(cls, path: str, block: Block, parent: Optional['Symbol'], category: Category, name: str) -> 'Symbol':
        if parent is None:
            parent_id = None
        else:
            assert isinstance(parent, Symbol)
            parent_id = parent.id

        symbol = cls(
            path=path,
            block=block,
            parent=parent_id,
            category=category,
            name=name,
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


class CodeMap(BaseModel):
    """The code map is a directed graph of symbols and their relations

    The code map may contain cycles, should a circular dependency exists
    in the source code. Any recursive iteration must keep track of visited
    symbols and handle cycles in finite time.

    """
    symbols: Dict[Identifier, Symbol]
    original_sources: Dict[str, Document]

    @classmethod
    def new(cls) -> 'CodeMap':
        return cls(symbols={}, original_sources={})

    @classmethod
    def from_working_copy(cls, wc: WorkingCopy, paths: Set[str]) -> 'CodeMap':
        from aidev.code_map.parsers import detect_parser

        code_map = cls.new()
        for path in paths:
            full_path = os.path.join(wc.project_dir, path)
            parser_cls = detect_parser(full_path)
            if parser_cls is None:
                continue
            parser = parser_cls()
            content = read_binary_file(full_path)
            parser.parse(code_map, path, content)
            code_map.original_sources[path] = Document.from_file(wc.project_dir, path)

        code_map.cross_reference()
        return code_map

    def update(self, other: 'CodeMap'):
        assert isinstance(other, CodeMap)

        conflicts: Set[Identifier] = set(self.symbols) & set(other.symbols)
        if conflicts:
            raise ValueError(f'Conflicting symbols: {sorted(conflicts)!r}')

        self.symbols.update(other.symbols)

    def new_source(self, path: str, file_line_count: int):
        symbol: Symbol = Symbol.new(path, Block.from_range(0, file_line_count), None, Category.SOURCE, path)
        self.symbols[symbol.id] = symbol
        return symbol

    def new_symbol(self, parent: Symbol, category: Category, name: str, block: Block) -> Symbol:
        symbol: Symbol = Symbol.new(parent.path, block, parent, category, name)
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
            if symbol.parent is None:
                return None
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

    def walk_children(self, parent: Symbol, depth: int = 0, visited: Optional[Set[Identifier]] = None) -> Iterable[
        Tuple[Symbol, int]]:
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

    def walk_dependencies(self, symbol: Symbol, depth: int = 0, visited: Optional[Set[Identifier]] = None) -> Iterable[
        Tuple[Symbol, int]]:
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

    def walk_dependants(self, symbol: Symbol, depth: int = 0, visited: Optional[Set[Identifier]] = None) -> Iterable[
        Tuple[Symbol, int]]:
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

    def iter_related_symbols(self, symbols: Iterable[Symbol]) -> Iterable[Symbol]:
        for symbol in symbols:
            yield from self.iter(symbol.dependencies)
            yield from self.iter(symbol.dependents)

    def iter_dependency_symbols(self, symbols: Iterable[Symbol]) -> Iterable[Symbol]:
        for symbol in symbols:
            yield from self.iter(symbol.dependencies)

    def iter_dependent_symbols(self, symbols: Iterable[Symbol]) -> Iterable[Symbol]:
        for symbol in symbols:
            yield from self.iter(symbol.dependents)

    def collect_symbols_from_text(self, text: str, categories: Set[Category]) -> Iterable[Symbol]:
        names = {m.group(0) for m in RX_NAMES.finditer(text)}
        for symbol in self.symbols.values():
            if symbol.category in categories and symbol.name in names:
                yield symbol

    def collect_relevant_sources(self, relevant_symbols: Set[Symbol]) -> Tuple[List[Symbol], List[Hunk], Set[str]]:
        function_symbols = {self.find_parent(symbol, Category.FUNCTION) for symbol in relevant_symbols if symbol.parent is not None}
        function_symbols = {symbol for symbol in function_symbols if symbol is not None}
        relevant_symbols.update(function_symbols)

        relevant_symbol_ids = {symbol.id for symbol in relevant_symbols}
        relevant_source_set = {self.find_parent(symbol, Category.SOURCE) for symbol in relevant_symbols if symbol.parent is not None}
        relevant_sources: List[Symbol] = sorted(relevant_source_set, key=lambda source: source.name)

        relevant_hunks: List[Hunk] = []
        for source in relevant_sources:
            document = self.original_sources[source.name]

            relevant_blocks: List[Block] = []
            for symbol, depth in self.walk_children(source):
                if symbol.id in relevant_symbol_ids:
                    relevant_blocks.append(symbol.block)

            assert relevant_blocks, f'No relevant blocks found in source: {source.name}'

            # Add using statements, the LLM must know these
            for using in self.iter_children_of_category(source, Category.USING):
                relevant_blocks.append(using.block)

            # Add the top level namespace, the LLM must know these
            for namespace in self.iter_children_of_category(source, Category.NAMESPACE):
                block = namespace.block
                if block.end - block.begin < 2:
                    continue

                for i in range(namespace.block.begin, namespace.block.end):
                    if '{' in document.lines[i]:
                        break
                else:
                    continue

                for j in range(namespace.block.end - 1, i - 1, -1):
                    if '}' in document.lines[j]:
                        break
                else:
                    continue

                relevant_blocks.append(Block.from_range(namespace.block.begin, i + 1))
                relevant_blocks.append(Block.from_range(j, namespace.block.end))

            relevant_blocks.sort(key=lambda b: b.begin)

            merged_blocks = [relevant_blocks[0]]
            for b in relevant_blocks[1:]:
                last = merged_blocks[-1]
                if b.end <= last.end:
                    continue
                if b.begin < last.end:
                    merged_blocks.append(Block.from_range(last.end, b.end))
                    continue
                merged_blocks.append(Block.from_range(b.begin, b.end))

            hunks = [Hunk.from_document(document, b) for b in merged_blocks]
            patch = Patch.from_hunks(document, hunks)
            patch.merge_hunks()
            hunk = patch.hunks[0]
            relevant_hunks.append(hunk)

        return relevant_sources, relevant_hunks, relevant_symbol_ids

    def cross_reference(self):
        self.__remove_external_references()
        namespace_symbol_map: NamespaceSymbolMap = self.__map_symbols_to_namespaces()
        self.__reference_symbols(namespace_symbol_map)
        self.__cleanup(namespace_symbol_map)
        self.__verify()

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
            parent.children.remove(symbol.id)
            del self.symbols[id]

    def __verify(self):
        for symbol in self.symbols.values():

            for id in symbol.children:
                if id not in self.symbols:
                    print(f'MISSING child {id!r} in parent {symbol.id!r}')

            for id in symbol.dependencies:
                if id not in self.symbols:
                    print(f'MISSING dependency {id!r} in symbol {symbol.id!r}')

            for id in symbol.dependents:
                if id not in self.symbols:
                    print(f'MISSING dependent {id!r} in symbol {symbol.id!r}')
