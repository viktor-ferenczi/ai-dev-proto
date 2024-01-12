import json
import random
from typing import Set

from lark import Lark, UnexpectedEOF, UnexpectedCharacters

LIST_GRAMMAR = Lark(r'''
?start: _WS? array _WS?

?array: value (_WS? "," _WS? value)*
value: SIGNED_NUMBER -> number

%import common.WS -> _WS
%import common.SIGNED_NUMBER
''')

JSON_IMPORTS = '''
%import common.ESCAPED_STRING
%import common.SIGNED_NUMBER
%import common.WS -> _WS
'''

JSON_GRAMMAR = Lark(r'''
?start: value

?value: object
      | array
      | string
      | SIGNED_NUMBER      -> number
      | "true"             -> true
      | "false"            -> false
      | "null"             -> null

array  : "[" _WS? [value ("," _WS? value)*] "]"
object : "{" _WS? [pair ("," _WS? pair)*] "}"
pair   : string ":" _WS value

string : ESCAPED_STRING
''' + JSON_IMPORTS)


DATA = {
    'a': [1, 2, 3],
    'b': {
        'minus two': -2,
        'pi': 3.14
    }
}

NEXT_TOKENS = [
    ' ',
    '1',
    '.',
    '+',
    '-',
    'x',
    '_',
    '"',
    ':',
    '{',
    '}',
    '[',
    ']',
]


def full():
    print('Full')
    j = json.dumps(DATA)
    p = JSON_GRAMMAR.parse(j)
    print(p.pretty())
    print('---')


def list_of_ints():
    print('List of ints')

    t = '   123 , 234,345 ,456, 567 '
    print(t)

    p = LIST_GRAMMAR.parse(t)

    if p is not None:
        print(p.pretty())
    print('---')


def find_next(g: Lark, t: str, allowed: Set[str]) -> str:
    if allowed == {'ESCAPED_STRING'} or allowed == {'STRING'}:
        return NEXT_TOKENS[0]

    for n in NEXT_TOKENS:
        j = t + n
        try:
            g.parse(j)
        except UnexpectedCharacters:
            pass
        except UnexpectedEOF:
            return n
        else:
            return n
    return ''


def continuation(seed: int):
    print('Continuation')
    rng = random.Random(seed)

    t = json.dumps(DATA)[:37]
    print(t)

    p = None
    for _ in range(50):
        try:
            p = JSON_GRAMMAR.parse(t)
            break
        except UnexpectedEOF as e:
            allowed = e.expected
        except UnexpectedCharacters as e:
            allowed = e.allowed

        rng.shuffle(NEXT_TOKENS)
        n = find_next(JSON_GRAMMAR, t, allowed)
        if not n:
            raise ValueError(f'Cannot find suitable next token, allowed ones: {allowed!r}')

        print(f'Allowed: {allowed}')
        print(f'Next: {n}')
        t += n
        print(t)

    if p is not None:
        print(p.pretty())

    print('---')


def main():
    full()
    list_of_ints()
    continuation(12345)


if __name__ == '__main__':
    main()
