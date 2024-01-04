# API: https://github.com/openai/openai-python
import os
import time

import unittest

from aidev.common.async_helpers import map_async, iter_async
from aidev.engine.engine import Engine
from aidev.engine.openai_engine import OpenAIEngine
from aidev.engine.params import GenerationParams

CONTEXT_HEADROOM_TOKENS = 100

SCRIPT_DIR = os.path.dirname(__file__)


def load_text(filename: str) -> str:
    with open(os.path.join(SCRIPT_DIR, filename), 'rt', encoding='utf-8-sig') as f:
        return f.read().replace('\r\n', '\n').replace('\r', '')


def crop_text(engine: Engine, text: str, max_tokens: int, separator: str = '\n\n') -> str:
    assert max_tokens > 0
    paragraphs = []
    total_tokens = 0
    start = 0
    more = True
    while more and total_tokens < max_tokens:
        end = text.find(separator, start)
        if end < 0:
            break

        end += len(separator)
        paragraph = text[start:end]

        paragraph_tokens = engine.count_tokens(paragraph)
        if separator != '. ' and total_tokens + paragraph_tokens > max_tokens:
            paragraph = crop_text(engine, paragraph, max_tokens - total_tokens, '. ')
            paragraph_tokens = engine.count_tokens(paragraph)
            more = False

        if total_tokens + paragraph_tokens > max_tokens:
            break

        paragraphs.append(paragraph)
        total_tokens += paragraph_tokens

        start = end

    result = ''.join(paragraphs)
    assert engine.count_tokens(result) <= max_tokens, (engine.count_tokens(result), max_tokens)
    return result


# This test works only with DeepSeek's tokenizer
# assert crop_text(OpenAIEngine(), 'First. Paragraph.\n\nSecond. Paragraph.\n\nThird. Paragraph.', 14) == 'First. Paragraph.\n\nSecond. '

BOOK = load_text('pg18857.txt')
BOOK = BOOK[BOOK.find('CHAPTER 1\n'):]

SYSTEM_CODEULATOR = '''\
MODEL ADOPTS ROLE OF CODEULATOR.
[CONTEXT: U LOVE TO CODE!]
[CODE]:
1.[Fund]: 1a.CharId 1b.TskDec 1c.SynPrf 1d.LibUse 1e.CnAdhr 1f.OOPBas 
2.[Dsgn]: 2a.AlgoId 2b.CdMod 2c.Optim 2d.ErrHndl 2e.Debug 2f.OOPPatt 
3.[Tst]: 3a.CdRev 3b.UntTest 3c.IssueSpt 3d.FuncVer 3e.OOPTest 
4.[QualSec]: 4a.QltyMet 4b.SecMeas 4c.OOPSecur 
5.[QA]: 5a.QA 5b.OOPDoc 6.[BuiDep]: 6a.CI/CD 6b.ABuild 6c.AdvTest 6d.Deploy 6e.OOPBldProc 
7.[ConImpPrac]: 7a.AgileRetr 7b.ContImpr 7c.OOPBestPr 
8.[CodeRevAna]: 8a.PeerRev 8b.CdAnalys 8c-CdsOptim 8d.Docs 8e.OOPCdRev
'''

INSTRUCTION_DEDUPLICATE_FILES = '''\
Your task is to write a Python 3 function to identify duplicate files in a folder and return a summary of them.

Requirements:
- At any depth in the subdirectory structure.
- Two files are duplicates if they have the same size and contents.
- File contents can be checked based on their SHA256 hashes (checksums).
- Do not read whole files into memory, calculate the hash in 32kB chunks.
- The risk of a hash collision is acceptable in this use case.
- Must find all duplicate files.
- Must NOT delete any files.
- The return value of the function must be a dictionary. The key must be the tuple of (file_size, checksum), values are the list of paths. Returns ONLY the duplicates, where there are at least two files in the list.
- The solution must work on both Windows and UNIX (Linux, MAC).
- Do not calculate the checksum of files with a unique size, because they cannot be duplicates.

Further instructions:
- Add only very concise comments into the code wherever it is absolutely necessary.
- Keep the code in each function short and as simple as possible.
- Avoid deep nesting of flow control.
- Factor the code into separate classes, methods or functions as needed to keep them simple to understand individually.
- Avoid assigning variables which are not used afterwards.
- Structure the code to be very easy to read and understand by humans.
- Add type hints to all function parameters, return values and variables.
- Provide only the code and nothing else.
- You are an expert developer, you can code this simple task very well.
'''

# Questions taken from https://codeburst.io/100-coding-interview-questions-for-programmers-b1cf74885fb7
QUESTIONS = [
    'How is a bubble sort algorithm implemented?',
    'How is a merge sort algorithm implemented?',
    'How do you count the occurrence of a given character in a string?',
    'How do you print the first non-repeated character from a string?',
    'How do you convert a given String into int like the atoi()?',
    'How do you implement a bucket sort algorithm?',
    'How do you implement a counting sort algorithm?',
    'How do you remove duplicates from an array in place?',
    'How do you reverse an array in place in Java?',
    'How are duplicates removed from an array without using any library?',
    'How is a radix sort algorithm implemented?',
    'How do you swap two numbers without using the third variable?',
    'How do you check if two rectangles overlap with each other?',
    'How do you design a vending machine?',
    'How do you find the missing number in a given integer array of 1 to 100?',
    'How do you find the duplicate number on a given integer array?',
    'How do you find duplicate numbers in an array if it contains multiple duplicates?',
    'Difference between a stable and unstable sorting algorithm?',
    'How is an iterative quicksort algorithm implemented?',
    'How do you find the largest and smallest number in an unsorted integer array?',
    'How do you reverse a linked list in place?',
    'How to add an element at the middle of the linked list?',
    'How do you sort a linked list in Java?',
    'How do you find all pairs of an integer array whose sum is equal to a given number?',
    'How do you implement an insertion sort algorithm?',
    'How are duplicates removed from a given array in Java?',
    'how to remove the duplicate character from String?',
    'How to find the maximum occurring character in a given String?',
    'How is an integer array sorted in place using the quicksort algorithm?',
    'How do you reverse a given string in place?',
    'How do you print duplicate characters from a string?',
    'How do you check if two strings are anagrams of each other?',
    'How do you find all the permutations of a string?',
    'How can a given string be reversed using recursion?',
    'How do you check if a given string is a palindrome?',
    'How do you find the length of the longest substring without repeating characters?',
    'Given string str, How do you find the longest palindromic substring in str?',
    'How do you check if a string contains only digits?',
    'How to remove Nth Node from the end of a linked list?',
    'How to merge two sorted linked lists?',
    'How to convert a sorted list to a binary search tree?',
    'How do you find duplicate characters in a given string?',
    'How do you count the number of vowels and consonants in a given string?',
    'How do you reverse words in a given sentence without using any library method?',
    'How do you check if two strings are a rotation of each other?',
    'How to convert a byte array to String?',
    'How do you remove a given character from String?',
    'How do you find the middle element of a singly linked list in one pass?',
    'How do you check if a given linked list contains a cycle? How do you find the starting node of the cycle?',
    'How do you reverse a linked list?',
    'How do you reverse a singly linked list without recursion?',
    'How are duplicate nodes removed in an unsorted linked list?',
    'How do you find the length of a singly linked list?',
    'How do you find the third node from the end in a singly linked list?',
    'How do you find the sum of two linked lists using Stack?',
    'What is the difference between array and linked list?',
    'How to remove duplicates from a sorted linked list?',
    'How to find the node at which the intersection of two singly linked lists begins.',
    'Given a linked list and a value x, partition it such that all nodes less than x come before nodes greater than or equal to x.',
    'How to check if a given linked list is a palindrome?',
    'How to remove all elements from a linked list of integers which matches with given value?',
    'How is a binary search tree implemented?',
    'How do you perform preorder traversal in a given binary tree?',
    'How do you traverse a given binary tree in preorder without recursion?',
    'How do you perform an inorder traversal in a given binary tree?',
    'How do you print all nodes of a given binary tree using inorder traversal without recursion?',
    'How do you implement a postorder traversal algorithm?',
    'How do you traverse a binary tree in postorder traversal without recursion?',
    'How are all leaves of a binary search tree printed?',
    'How do you count a number of leaf nodes in a given binary tree?',
    'How do you perform a binary search in a given array?',
    'How to Swap two numbers without using the third variable?',
    'How to check if two rectangles overlap with each other?',
    'How to design a Vending Machine?',
    'How to implement an LRU Cache in your favorite programming language?',
    'How to check if a given number is a Palindrome?',
    'How to check if a given number is an Armstrong number?',
    'How to find all prime factors of a given number?',
    'How to check if a given number is positive or negative in Java?',
    'How to find the largest prime factor of a given integral number?',
    'How to print all prime numbers up to a given number?',
    'How to print Floyd’s triangle?',
    'How to print Pascal’s triangle?',
    'How to calculate the square root of a given number?',
    'How to check if the given number is a prime number?',
    'How to add two numbers without using the plus operator in Java?',
    'How to check if a given number is even/odd without using the Arithmetic operator?',
    'How to print a given Pyramid structure?',
    'How to find the highest repeating world from a given file in Java?',
    'How to reverse a given Integer in Java?',
    'How to convert a decimal number to binary in Java?',
    'How to check if a given year is a leap year in Java?',
    'Can you implement a Binary search Algorithm without recursion?',
    'Difference between a stable and unstable sorting algorithm?',
    'What is Depth First Search Algorithm for a binary tree?',
    'How is an iterative quicksort algorithm implemented?',
    'How do you implement an insertion sort algorithm?',
    'How is a merge sort algorithm implemented?',
    'What is the difference between Comparison and Non-Comparison Sorting Algorithms?',
    'How do implement Sieve of Eratosthenes Algorithms for Prime Number?',
]


class EngineTest(unittest.IsolatedAsyncioTestCase):

    async def test_single_completion(self):
        engine = OpenAIEngine()
        system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
        instruction = 'How is an iterative quicksort algorithm implemented?'
        params = GenerationParams(max_tokens=300)

        started = time.perf_counter()
        completions = await engine.generate(system, instruction, params)
        finished = time.perf_counter()
        duration = finished - started

        self.assertEqual(1, len(completions))
        completion = completions[0]
        token_count = engine.count_tokens(completion)

        usage = engine.usage
        self.assertEqual(1, usage.generations)
        self.assertEqual(1, usage.completions)
        self.assertEqual(token_count, usage.completion_tokens + 1)
        self.assertGreater(usage.prompt_tokens, 0)

        print(f'Generated {usage.completion_tokens} tokens in {duration:.1f}s ({usage.completion_tokens / duration:.1f} tokens/s)')
        print(f'Output:\n{completion}')

    async def test_multiple_completions(self):
        engine = OpenAIEngine()
        system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
        instruction = 'How is an iterative quicksort algorithm implemented?'
        params = GenerationParams(max_tokens=300, number_of_completions=16)

        started = time.perf_counter()
        completions = await engine.generate(system, instruction, params)
        finished = time.perf_counter()
        duration = finished - started

        self.assertEqual(params.number_of_completions, len(completions))

        usage = engine.usage
        print(f'Generated {usage.completion_tokens} tokens in {duration:.1f}s ({usage.completion_tokens / duration:.1f} tokens/s)')

        for index, completion in enumerate(completions):
            print(f'Output {index}:\n{completion}\n\n')
            self.assertTrue(bool(completion.strip()))

    async def test_coding(self):
        engine = OpenAIEngine()
        params = GenerationParams(max_tokens=2000)

        print('SYSTEM:')
        print(SYSTEM_CODEULATOR)
        print()

        print('INSTRUCTION:')
        print(INSTRUCTION_DEDUPLICATE_FILES)
        print()

        started = time.perf_counter()
        completions = await engine.generate(SYSTEM_CODEULATOR, INSTRUCTION_DEDUPLICATE_FILES, params)
        finished = time.perf_counter()
        duration = finished - started

        self.assertEqual(1, len(completions))

        completion = completions[0]

        usage = engine.usage
        print(f'Generated {usage.completion_tokens} tokens in {duration:.1f}s ({usage.completion_tokens / duration:.1f} tokens/s)')

        print(f'COMPLETION:\n{completion}')

        self.assertTrue(bool(completion.strip()))

    async def test_long_context(self):
        engine = OpenAIEngine()

        for size in (1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536, 100000, 131072, 200000, 262144):
            if size > engine.max_context:
                break

            params = GenerationParams(max_tokens=400)
            text = crop_text(engine, BOOK, size - params.max_tokens - CONTEXT_HEADROOM_TOKENS)

            system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
            instruction = f'{text}\n\nPlease summarize the above text in 3 sentences.'

            system_tokens = engine.count_tokens(system)
            instruction_tokens = engine.count_tokens(instruction)

            print(f'{size:>6d}: {system_tokens} system + {instruction_tokens} instruction + {params.max_tokens} completion')
            completions = await engine.generate(system, instruction, params)
            completion = completions[0]

            self.assertTrue(bool(completion.strip()))

    async def test_parallel_load(self):
        engine = OpenAIEngine()

        system = "You are a helpful AI assistant. You give concise answers. If you do not know something, then say so."
        system_tokens = engine.count_tokens(system)

        async def generate(instruction: str) -> str:
            instruction_tokens = engine.count_tokens(instruction)
            params = GenerationParams(max_tokens=engine.max_context - system_tokens - instruction_tokens - CONTEXT_HEADROOM_TOKENS)
            completions = await engine.generate(system, instruction, params)
            return completions[0]

        started = time.perf_counter()
        outputs = [completions[0] async for completions in map_async(generate, iter_async(QUESTIONS), max_tasks=engine.optimal_parallel_sequences)]
        finished = time.perf_counter()
        duration = finished - started

        self.assertEqual(len(QUESTIONS), len(outputs))

        for output in outputs:
            self.assertTrue(bool(output.strip()))

        usage = engine.usage
        print(f'Generated {usage.completion_tokens} tokens in {duration:.1f}s ({usage.completion_tokens / duration:.1f} tokens/s)')
