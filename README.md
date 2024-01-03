# AI Developer

Tooling which allows LLMs to work on software projects along with human developers.

The intended use is to let the AI work on lots of the simple tasks, while the humans
can concentrate on design tasks and solving complex issues the AI cannot deal with yet.

The AI Dev works in a branch, committing fixes to each of the issues SonarQube found
in the code base. It re-analyzes the project after each change. The selection of the
OPEN issue to work on is random, so it is not stuck with an issue it cannot resolve.

Each issue is attempted 16 times each time (16 parallel completions) for efficiency.
This number is currently hardcoded and determined by the optimum throughput of our
locally hosted LLMs.

## Dependencies

### Python

Python version 3.10 or newer. Tested on 3.10.10.

### Python packages

#### Linux

```shell
pip -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

#### Windows
```cmd
pip -m venv venv
.\venv\Scripts\activate.bat
pip install -r requirements.txt
```

You must activate the Python virtual environment (venv) before 
running the CLI.

Alternatively you and install the packages directly into your 
default Python interpreter (globally). In that case the activation
of the Python virtual environment is not required.

## Configuration

### Environment

#### AIDEV_MODEL

Name of the model the LLM engine is running. This is used only to
select the correct tokenizer and chat template for APIs with a raw
prompt format, like vLLM.

The AI Developer currently requires an instruction fine-tuned chat
model (chat-instruct) to function correctly.

##### Valid values
- `codellama`
- `deepseek`

Default: `deepseek`

#### AIDEV_OPENAI_BASE_URL

The base URL of the OpenAI compatible API to use. The default value
is suitable of locally hosted models. 

If you want to use the OpenAI hosted models, then set this to:
`https://api.openai.com/v1`

Default: `http://127.0.0.1:8000/v1`

#### AIDEV_OPENAI_KEY

Set this to your OpenAI API key only if you want to use the OpenAI
hosted models. The locally hosted models do not required an API key. 

Default: `NO-KEY`

#### AIDEV_OPENAI_MODEL

The model name passed to the OpenAI compatible API. For our locally
hosted LLMs it is always `model`. It needs to be changed only if you
happen to connect the AI Developer to the real OpenAI API, where it
must be the ID of the model to use, like `gpt-3.5-turbo`.

Default: `model`

#### AIDEV_VLLM_BASE_URL

Base URL of the vLLM API to connecto to.

**FIXME:** Currently unused. Also, there is no AIDEV_ENGINE variable.

Default: `http://127.0.0.1:8000/v1`

#### SONAR_BASE_URL

Base URL of the SonarQube API to connect to.

Default: `http://127.0.0.1:9000`

#### SONAR_TOKEN

SonarQube API token to authenticate with.

Open **[My Account / Security](http://127.0.0.1:9000/account/security)** 
on the **SonarQube Web UI**. 

Generate a **User** token.

##### Linux

`export SONAR_TOKEN="squ_..."`

##### Windows

`set SONAR_TOKEN=squ_...` or add it in the Control Panel.

There is no default value. It is required to set this variable, currently.

### Analyzer

[Install SonarQube Scanner tool into your project](https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/sonarscanner-for-dotnet/)

Your project must have a script at its top level to run the scanner, currently.

## Usage

Make sure that the environment variables (see configuration above) are defined
and the Python virtual environment is activated (if you have one).

### Linux

```shell
cd "/path/to/ai-dev"
export PYTHONPATH=$(pwd)
python -O -u cli/cli.py -p /path/to/your/project -n SonarQubeProjectName
```

For example:

```shell
cd ~/ai-dev-proto
export PYTHONPATH=$(pwd)
python -O -u cli/cli.py -p ~/example-shop -n Shop
```

### Windows

```cmd
cd "C:\path\to\ai-dev"
set "PYTHONPATH=%cd%"
python -O -u cli/cli.py -p /path/to/your/project -n SonarQubeProjectName
```

For example:

```cmd
cd C:\Dev\AI\ai-dev-proto
set "PYTHONPATH=%cd%"
python -O -u cli\cli.py -p C:\Dev\AI\example-shop -n Shop
```

## Workflow

AI Dev currently supports .NET Core projects which successfully build and test. 

AI Dev creates a new branch of the given `name` (if it is not exists already),
switches to it. The project is auto-formatted using the `dotnet format` command.
The formatting is committed separately if it caused any changes. If the project
has already been formatted, then no initial commit is created for this.

Issues are selected randomly from the ones queried via the SonarQube API.
Issue resolution is attempted multiple times until the modified project 
can successfully build and test.

On successful resolution AI Dev auto-formats the project, then commits the
changes into the branch. The commit notes contain the SonarQube issue key 
and message for reference. It does not automatically push the branch.

It does not create more than one commit for the same issue, but resolving an
issue may create a new one which would be picked up as a new issue by SonarQube.
It may end up in a loop, but the random issue selection avoids the loop, unless
it is the very last issue to work on.

The suggested way to work with AI Dev is to let it solve issues in a separate
working copy for a few hours. Then review the changes in the local branch
created, revert the bad ones, then push the branch and create a PR for
other team members to review and merge.

## Limitations

Known limitations of this simple prototype.

- Can work only on a single file in each commit.
- Prepared to handle `.py`, `.cs` and `.cshtml` files, more are configurable.
- The LLM can make mistakes, accidentally remove code or comments.
- No support to build up test coverage (planned).
- The CLI has no commands yet, its arguments will change.
- With 16k maximum context size it can handle source files of up to 5000 tokens in size.
  (Later this will decrease to 3000.)

## Diagnostics

AI Dev creates a `.aidev` subdirectory in your project folder. It contains
information on all `attempts` in Markdown format. These files contain all
the internal information and help in solving problems with AI Dev's 
performance and improve its prompts and structured thinking.

There is also a `latest.md` file, which is the accepted completion 
corresponding to the source code changes in the same commit.

You are free to exclude these files from the repository by adding the
`.aidev` folder to `.gitignore`. You may still find committing `latest.md`
useful, because it can help explaining repeated failures.

## Statistics

None is collected, currently.

## Troubleshooting

In case of problems run the Python test cases in `tests/test_openai.py` to
verify the LLM API connectivity and the context size. 

There is also a simpler command line 
tool to prompt the LLM is also available: `tests/coding_openai.py```

If you see downloads from HuggingFace or transformer warnings, that only the
tokenizer, which is small. It does not download a full model.

Look into `common/config.py` to extend with new file types.