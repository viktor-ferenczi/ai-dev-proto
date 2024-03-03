"""Experiment to fix build errors

1. Start with a solution which can build just fine
2. Make a code map from the original code
3. Make a modification to the code intentionally introducing a non-trivial build error
4. Make a code map from the modified code
5. Build the solution and capture the error messages
6. Collect the known symbols from the error message
7. Collect the direct dependencies of those symbols
8. Collect the relevant parts of the source files which contain those symbols
9. Collect the corresponding parts of the original source files
10. Ask the LLM to fix the issue, include the relevant original and modified code
11. Re-integrate the modification into the modified code
12. Repeat from step 4. until the solution can build

Possible improvements:
- GoT by using multiple generations and going down multiple paths
- Scoring or comparing multiple fixes provided by the LLM to pick out the best

"""
import asyncio


async def main():
    pass


if __name__ == '__main__':
    asyncio.run(main())
