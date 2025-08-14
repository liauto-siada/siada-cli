# Contributing to Siada

We are very excited that you are interested in contributing to Siada. Before you begin, please understand our vision:

We have always believed that code development is just one aspect of software engineering. In the future, we hope to develop feature-complete vertical domain Agents and tools for more software engineering work scenarios, making programmers' work increasingly simple.

Although currently limited by model capabilities, most Agents still follow the "HUMAN-IN-THE-LOOP" design approach, the rapid development of AI technology shows us new possibilities. We are actively exploring "LOOP-WITHOUT-HUMAN" intelligent Agents, committed to providing end-to-end automation support in multiple aspects such as requirement analysis, code generation, test validation, and operations deployment, reducing manual intervention and truly liberating developers' productivity.

To this end, we will focus on the following directions:

- **Tool Empowerment**: Provide more software engineering tools that can be directly integrated into Agents, covering key scenarios such as development, testing, and deployment;

- **Development Efficiency**: Create lower-cost Agent development models to make building intelligent assistants more convenient;

- **Scenario Expansion**: Build more vertical domain Agents, gradually expanding Agent applications in software engineering from coding assistance to more actual workflows (such as automated testing, compilation, fault localization, documentation maintenance, etc.).

Ultimately, we hope that programmers can focus on more creative work, while tedious and repetitive tasks are left to AI Agents to complete—making programming simpler and innovation freer.

## Contributor Agreement
To avoid conflicts with open-source license agreements or infringement of others’ intellectual property rights, you must sign a Contributor License Agreement (CLA) before contributing code or documentation. You should send the signed agreement to the designated email address as specified in the CLA. This ensures that the code or documentation you contribute is your own original work, or that any third-party code you reference does not conflict with the Apache License 2.0.

[contributor agreement](./contributor_agreement.md)

## Project Directory Structure

This project adopts a standard Python project structure. The following are explanations of the core first-level directories:

### Core Code Directories
- **`siada/`** - Main source code directory, containing all core functional modules
  - `agent_hub/` - Agent collection, containing various specialized AI agents
  - `tools/` - Tool collection, providing various functional tools
  - `services/` - Service layer, containing core business logic
  - `provider/` - LLM provider adaptation layer
  - `entrypoint/` - Program entry points and command-line processing

### Testing and Benchmarks
- **`tests/`** - All test cases, following the same directory structure as the source code
- **`benchmark/`** - Performance benchmark tests and evaluation framework

### Development Recommendations
When contributing code, please follow the following directory usage principles:
- New feature code should be placed in the appropriate modules under `siada/`
- Corresponding test cases must be placed in the `tests/` directory, maintaining the same path structure as the source code
- Tool-related functionality should be prioritized for placement in the `siada/tools/` directory
- Vertical domain Agents should be prioritized for placement in the `siada/agent_hub/` directory

## Pull Request Guidelines

### 1. Associate with an Existing Issue
All PRs should be associated with an existing Issue in our issue tracker. This ensures that every change has been discussed before writing code and aligns with project goals.
- **Bug fixes**: PRs should link to the corresponding bug report Issue.
- **Adding features**: PRs should link to feature requests or proposal Issues that have been approved by maintainers.

If there is no corresponding Issue for your change, please submit an Issue first and wait for feedback before starting to write code.

### 2. Keep PRs Small and Focused
We encourage submitting small, atomic PRs that focus on solving a single problem or adding an independent feature.
- ✅ **Example**: Create a PR that only fixes one specific bug or adds one specific feature.
- ❌ **Avoid**: Packaging multiple unrelated changes (e.g., bug fixes, new features, refactoring) into one PR.

Large changes should be split into multiple small, logically clear PRs for independent review and merging.

### 3. Use Draft PRs for Work in Progress
If you want to get early feedback, please use GitHub's Draft Pull Request feature.
This indicates that the PR is not ready for formal review but welcomes discussion and preliminary opinions.

### 4. Ensure All Test Cases Pass
All PRs must pass the existing test suite before being merged.

#### Running Tests
We provide an automated test runner to help you run all tests easily:

```bash
# Run all tests
python tests/run_tests.py

# Run tests in quiet mode
python tests/run_tests.py --quiet

# List all test files without running them
python tests/run_tests.py --list
```

Alternatively, you can use pytest directly:

```bash
# Run all tests with pytest
pytest tests/

# Run tests with verbose output
pytest tests/ -v

# Run a specific test file
pytest tests/tools/test_example.py
```

#### Test File Naming Convention
All test files must follow the naming convention `test_*.py` to be automatically discovered by the test runner. For example:
- ✅ `test_file_operator.py`
- ✅ `test_fix_attempt_completion_formatter.py`
- ❌ `file_operator_test.py`
- ❌ `example_test.py`

#### Test Function Naming Convention
All test functions within test files must start with `test_` to be recognized by the testing framework. For example:
- ✅ `def test_file_creation():`
- ✅ `def test_error_handling():`
- ❌ `def check_file_creation():`
- ❌ `def validate_error_handling():`

#### Test Organization
- Test files should be placed in the `tests/` directory
- Test files should follow the same directory structure as the modules under test
- Each test file should focus on testing a specific module or functionality
- Use descriptive test names that clearly indicate what is being tested

### 5. Update Documentation
If your PR introduces user-facing changes (e.g., new commands, modified parameters, or behavior changes), you must also update the relevant documentation in the `/docs` directory.

### 6. Write Clear Commit Messages and PR Descriptions
Provide clear, descriptive commit messages and PR descriptions that explain what changes were made and why they were necessary.
