#### Reproduction Step

1.  Install `siada-cli` by following the [user guide](https://github.com/liauto-siada/siada-cli/tree/main).
2.  Execute the bug-fixing command:
    ```bash
    echo "execute no tty" | siada-cli --bugfix --prompt <issue_description>
    ```
    * Here, `<issue_description>` is the "problem statement" from swe-bench.
3.  Use `git diff` to obtain the fix patch. Apply this patch to the original repository containing the issue and run the test cases.

This submission is made with Siada CLI latest of the branch main using `anthropic/claude-sonnet-4-20250514`.

## 1. Introduction

**Siada CLI** is an open-source command-line AI workflow tool that provides professional intelligent agents for code development, debugging, and automation tasks. Among them, the **code generation agent** serves as the starting point for all agents within Siada CLI. We believe that code generation based on large language models has the potential to empower every stage of the software engineering lifecycle. Based on this belief, we conducted internal practices at **Li Auto** and open-sourced some capabilities in Siada CLI.

This report demonstrates how we applied Siada CLI to automatically solve problems in the **SWE-bench-Lite benchmark**. Unlike many existing methods that indiscriminately attempt to solve problems multiple times, we designed an adaptive code fixing method based on issue description responses, implementing intelligent workflow orchestration through issue description optimizers and classifiers for bug fix agents, checkers, and selectors. This method adaptively selects three repair modes (Easy, Middle, Hard) based on problem complexity, using fast generalization for simple problems and inference-time scaling techniques for complex problems.

In the SWE-bench-Lite benchmark, Siada CLI achieved a **60.67% problem resolution rate (182/300), ranking first among all currently listed methods**. The following sections will introduce the system design of the error fixing agent in Siada CLI. Our paper will be coming soon, and the following content is the technical documentation of the system design.

## 2. System Overview

### 2.1 Bug Fixing in Siada CLI

Initially, we designed a **multi-agent architecture** based on human engineer bug fixing processes and **TDD (Test-Driven Development)** principles. This included **issue reproduction agents**, **bug fix agents**, **test case agents**, etc., organized into specific problem-solving workflows. Despite continuous attempts to optimize these agents, the multi-agent combination approach did not achieve ideal results in the bug fixing domain. We believe the main reasons are:

- **Model capabilities are sufficiently powerful**: Current large language models can directly execute closed-loop tasks of reproduction, localization, fixing, and testing in a single session. Additional issue reproduction agents and test agents do not provide more incremental content for the bug fix agent.

- **Models still have significant shortcomings in agent switching**: After trying fixed workflows (reproduction→fixing→testing), we attempted to let models autonomously switch agents and decide when to use specific agents. However, actual results show that models currently struggle to perfectly implement such capabilities. Although frameworks like **openai-agent-sdk** and **adk** provide agent switching capabilities, we still believe current model capabilities cannot perfectly handle multi-agent tasks.

- **Single agents are more efficient**: Multi-agent approaches failed to improve accuracy for different types of bugs such as simple problem fixes and complex functional requirements during bug fixing, but significantly reduced efficiency and increased costs.

- **Single agents provide flexible adaptive testing**: During the fixing process, new test cases can be dynamically generated and executed more strategically.

However, single-agent mode alone is insufficient to achieve excellent results. Therefore, we designed an adaptive code fixing method based on issue description responses, implementing intelligent workflow orchestration through issue description optimizers and classifiers for bug fix agents, checkers, and selectors. This method adaptively selects three repair modes (Easy, Middle, Hard) based on problem complexity, using fast generalization for simple problems and inference-time scaling techniques for complex problems. The inspiration for this method comes from:

1. **Regarding issue description optimization and classification**: Issue description optimization and classification includes two steps: issue description optimization and issue description classification. For issue description optimization, it is well known that challengers can more easily achieve high scores on the **swe-bench-verified** leaderboard. An important reason for this phenomenon is that the issue descriptions in verification cases are manually annotated. Therefore, we wondered if we could have models automatically "annotate" issue descriptions.
For description classification, during software development and maintenance processes, development teams receive a large number of issue tickets through defect tracking systems (such as Jira, Bugzilla). These tickets contain various real bugs, feature improvement requirements, code refactoring suggestions, performance optimizations, and other issues. Researchers have proposed automatic classification through issue descriptions (issue tickets) to achieve automated task allocation and development cycle planning, which is crucial for efficient bug handling. Inspired by this, we propose a bug issue description classifier, which is a RandomForestClassifier responsible for evaluating problem complexity. At the same time, we analyzed over 500,000 calls to Li Auto's internal code generation tool from April to September 2025, classifying issue descriptions into Easy, Middle, and Hard levels. Classification decisions are based on multi-dimensional feature analysis: **Semantic complexity analysis**: Analyzing semantic features such as concept complexity and logical relationship complexity involved in issue descriptions. **Technical difficulty assessment**: Evaluating the depth of technical knowledge required for fixing, including the number of APIs involved, framework complexity, algorithm difficulty, etc. **Code impact scope**: Estimating the code scope that fixing might affect, including the number of files, functions, inter-module dependencies, etc. **Historical fixing data**: Using patterns in historical fixing data to assist classification decisions, as well as emotional tone words related to issue difficulty.

2. **Regarding patch checking**: Based on previous multi-agent experiments, we found that if subsequent agents continue the work of previous agents, they must trust the work of previous agents to some extent, which creates "inertial thinking." If previous agents have problems, all subsequent work becomes meaningless (this is also one of the reasons why fixed workflow multi-agent methods perform poorly). Therefore, we believe someone needs to stand on the opposite side of the bug fix agent, forget the bug fix agent's work process, and then review its fixing results. Therefore, we added a patch checking stage.

3. **Regarding three repair modes**: Through analysis of real-world code generation requirements and descriptions, we believe that among the problems related to issue descriptions, some simple problems can be solved through relatively concise workflows, corresponding to our easy mode. Therefore, when problems are classified as simple problems, we use a workflow of issue description optimization→error fixing to solve them. Another part of problems, we believe the model may miss important boundary conditions during fixing, so corresponding to middle mode, we use a workflow of issue description optimization→error fixing→patch checking to solve them. Finally, some problems with relatively vague descriptions or inherently difficult problems correspond to hard mode. After issue description optimization, we use multiple error fixes to obtain multiple results and use a selector to choose a more appropriate result through testing and comparison.

Therefore, we designed an adaptive code fixing method based on issue description responses, implementing intelligent workflow orchestration through issue description optimizers and classifiers for bug fix agents, checkers, and selectors. This method adaptively selects three repair modes (Easy, Middle, Hard) based on problem complexity. The design of issue description optimizers and classifiers for bug fix agents, checkers, and selectors will be introduced in sections 2.2, 2.3, 2.4, and 2.5 respectively.

### 2.2 Issue Description Optimization and Classification Stage

### 2.2.1 Issue Description Optimization Steps
To reduce the negative impact of ambiguous task descriptions, we propose an **issue description optimizer**. It directly receives the original issue description and, based on preset prompt templates, uses LLM to generate more complete and precise structured error reports.

#### (1) Specific Optimization Content
The optimizer performs multi-dimensional enhancement of the original description as follows:
- **Potential Issue Identification**: Not only focuses on explicit errors, but also infers potential root causes and analyzes technical details in error messages.

- **Test Scenario Clarification**: Lists various input forms and boundary conditions to ensure comprehensive test coverage.

- **Expected Behavior Definition**: Clearly defines how the system should correctly handle different inputs, rather than merely preventing errors.

- **Complete Reproduction Steps**: Provides directly executable code examples covering multiple data formats.

- **Acceptance Criteria Formulation**: Quantifies conditions for successful fixes, such as all related tests passing, maintaining backward compatibility, and meeting mathematical/business specifications.

#### (2) Case Analysis
**Original Issue Description:**

```python
I think this is a bug.

I created a matrix by M.T * M under an assumption that M is orthogonal. SymPy successfully recognized that the result is an identity matrix. I tested its identity-ness by element-wise, queries, and sum of the diagonal elements and received expected results.

However, when I attempt to evaluate the total sum of the elements the result was 0 while 'n' is expected.

from sympy import *
from sympy import Q as Query

n = Symbol('n', integer=True, positive=True)
i, j = symbols('i j', integer=True)
M = MatrixSymbol('M', n, n)

e = None
with assuming(Query.orthogonal(M)):
    e = refine((M.T * M).doit())

# Correct: M.T * M is an identity matrix.
print(e, e[0, 0], e[0, 1], e[1, 0], e[1, 1])

# Correct: The output is True True
print(ask(Query.diagonal(e)), ask(Query.integer_elements(e)))

# Correct: The sum of the diagonal elements is n
print(Sum(e[i, i], (i, 0, n-1)).doit())

# So far so good
# Total sum of the elements is expected to be 'n' but the answer is 0!
print(Sum(Sum(e[i, j], (i, 0, n-1)), (j, 0, n-1)).doit())
```

**Optimized Issue Description:**

```markdown
# Bug Report: Incorrect Sum Calculation for Identity Matrix Elements
## Issue Overview
SymPy incorrectly calculates the total sum of all elements in an identity matrix as 0 instead of the expected value n (where n is the matrix dimension). This occurs when the identity matrix is derived through symbolic matrix operations with orthogonality assumptions.

## Detailed Problem Description

### Root Cause Analysis
The issue appears to stem from inconsistent handling of symbolic identity matrices in SymPy's summation evaluation logic. While SymPy correctly:
- Recognizes the matrix as an identity matrix through `refine()`
- Handles individual element access (`e[i,j]`)
- Calculates diagonal sum correctly
- Identifies matrix properties (diagonal, integer elements)

It fails when evaluating the double summation over all matrix elements. This suggests a disconnect between the symbolic representation of the identity matrix and the summation evaluation engine's understanding of that representation.

### Technical Details
- The matrix `e` is created via `refine((M.T * M).doit())` under orthogonality assumptions
- Individual element queries work correctly (returning 1 for diagonal, 0 for off-diagonal)
- Single summation over diagonal elements correctly yields `n`
- Double summation over all elements incorrectly yields `0` instead of `n`

## Reproduction Steps

### Scenario 1: Basic Identity Matrix from Orthogonal Matrix (Original Case)
```python
from sympy import *
from sympy import Q as Query

n = Symbol('n', integer=True, positive=True)
i, j = symbols('i j', integer=True)
M = MatrixSymbol('M', n, n)

e = None
with assuming(Query.orthogonal(M)):
    e = refine((M.T * M).doit())

# Verify identity matrix properties
print("Matrix:", e)
print("Element access:", e[0, 0], e[0, 1], e[1, 0], e[1, 1])
print("Matrix properties:", ask(Query.diagonal(e)), ask(Query.integer_elements(e)))

# Test summations
diagonal_sum = Sum(e[i, i], (i, 0, n-1)).doit()
total_sum = Sum(Sum(e[i, j], (i, 0, n-1)), (j, 0, n-1)).doit()

print("Diagonal sum (expected n):", diagonal_sum)
print("Total sum (expected n, actual):", total_sum)

### Scenario 2: Direct Identity Matrix Creation
```python
from sympy import *

n = Symbol('n', integer=True, positive=True)
i, j = symbols('i j', integer=True)

# Create identity matrix directly
I = Identity(n)

diagonal_sum = Sum(I[i, i], (i, 0, n-1)).doit()
total_sum = Sum(Sum(I[i, j], (i, 0, n-1)), (j, 0, n-1)).doit()

print("Direct Identity - Diagonal sum:", diagonal_sum)
print("Direct Identity - Total sum:", total_sum)


## Expected Behavior

### Correct Handling Requirements
1. **Identity Matrix Recognition**: All forms of identity matrices (direct creation, derived from orthogonal assumptions) should behave consistently
2. **Summation Consistency**: Total sum of identity matrix elements should always equal the matrix dimension `n`
3. **Element Access Consistency**: Individual element access and summation results should be mathematically consistent
4. **Multiple Input Formats**: The fix should work for:
   - Identity matrices created via `Identity(n)`
   - Identity matrices derived from `refine((M.T * M).doit())` under orthogonality assumptions
   - Both symbolic and numeric dimensions

### Mathematical Correctness
For an n×n identity matrix:
- Diagonal elements: `I[i,i] = 1` for all valid i
- Off-diagonal elements: `I[i,j] = 0` for i ≠ j  
- Diagonal sum: `Σ(i=0 to n-1) I[i,i] = n`
- Total sum: `Σ(i=0 to n-1)Σ(j=0 to n-1) I[i,j] = n`

## Acceptance Criteria

### Must Satisfy All Conditions:
1. **Correct Total Sum**: `Sum(Sum(e[i, j], (i, 0, n-1)), (j, 0, n-1)).doit()` returns `n`
2. **Preserved Functionality**: All existing correct behaviors remain unchanged:
   - Individual element access works correctly
   - Diagonal sum calculation remains correct
   - Matrix property queries work correctly
3. **Cross-Method Consistency**: Results are consistent across different creation methods:
   - Direct `Identity(n)` creation
   - Derived identity matrices from orthogonal assumptions
4. **Numeric Verification**: Fix works for both symbolic (`n`) and concrete numeric dimensions
5. **Summation Order Independence**: Results are identical regardless of summation order (i,j vs j,i)
6. **Performance**: No significant performance regression in matrix operations
7. **Edge Cases**: Proper handling of:
   - `n = 1` (1×1 identity matrix)
   - Large symbolic dimensions
   - Mixed symbolic/numeric expressions

### Verification Tests
All reproduction scenarios above should pass, with total sums correctly evaluating to the matrix dimension rather than 0.
```

**Without Optimizer – Over-modified Changes (Wrong Fix Example):**

Problems:
- Multiple unrelated modules touched
- Regression risk
- Not targeted at root cause

```diff
diff --git a/sympy/assumptions/sathandlers.py b/sympy/assumptions/sathandlers.py
+try:
+    from collections.abc import MutableMapping
+    from collections import defaultdict
+except ImportError:
+    from collections import MutableMapping, defaultdict

diff --git a/sympy/concrete/summations.py b/sympy/concrete/summations.py
+        # Added complex Piecewise handling logic unrelated to the bug...

diff --git a/sympy/core/basic.py b/sympy/core/basic.py
+try:
+    from collections.abc import Mapping
+except ImportError:
+    from collections import Mapping

diff --git a/sympy/matrices/expressions/matexpr.py b/sympy/matrices/expressions/matexpr.py
-        if i == j:
-            return S.One
-        else:
-            return S.Zero
+        # Unrelated change mixed with other modules
```

**With Optimizer – Minimal & Precise Fix (Correct Fix Example):**

```diff
diff --git a/sympy/matrices/expressions/matexpr.py b/sympy/matrices/expressions/matexpr.py
@@ def _entry(self, i, j):
-        if i == j:
-            return S.One
-        else:
-            return S.Zero
+        from sympy.functions.special.tensor_functions import KroneckerDelta
+        return KroneckerDelta(i, j)
```

We believe that: **Bug description optimization provides significant guidance in problem root cause analysis, reproduction steps, edge case coverage, and regression testing.**

### 2.2.2 Issue Description Classification Steps

The classifier uses a machine learning model (RandomForestClassifier) based on text analysis, combined with a rule engine to achieve accurate complexity assessment. The classification results directly determine the subsequent repair strategy:
- **Easy mode**: Suitable for simple logical errors, API usage errors, etc., using fast generalization strategies.
- **Middle mode**: Suitable for medium complexity problems, using iterative optimization strategies.
- **Hard mode**: Suitable for complex systemic problems, using multi-candidate generation and selection strategies. In actual implementation, we use anomaly detection as the classifier implementation, where the is_easy field in logs represents the classification result: 0 for easy, 1 for middle, and 2 for hard.

The training data for this classifier is extracted from our internal code generation requirement data, which is similar to the problem descriptions in the lite dataset. The extracted relevant features are shown in the following table, and we have open-sourced this model weights in Siada CLI.

#### Detailed Feature Table

| No. | Feature Name | Calculation Method | Feature Type | Data Type | Example Value | Description |
|-----|--------------|-------------------|--------------|-----------|---------------|-------------|
| 0 | `char_count` | `len(problem_content)` | Basic Statistics | int | 1250 | Total character count |
| 1 | `word_count` | `len(words)` | Basic Statistics | int | 180 | Total word count |
| 2 | `line_count` | `len(problem_content.split('\n'))` | Basic Statistics | int | 15 | Total line count |
| 3 | `sentence_count` | Split by `.!?` and count sentences | Basic Statistics | int | 8 | Total sentence count |
| 4 | `avg_word_length` | `np.mean([len(word) for word in words])` | Language Complexity | float | 5.2 | Average word length |
| 5 | `unique_word_ratio` | `len(set(words)) / len(words)` | Language Complexity | float | 0.75 | Unique word ratio |
| 6 | `project_mentions` | Project keyword count | Project Specific | int | 3 | Project-related keyword occurrences |
| 7 | `error_mentions` | Error keyword count | Problem Analysis | int | 2 | Error-related keyword occurrences |
| 8 | `tech_mentions` | Technical term count | Technical Content | int | 5 | Technical term occurrences |
| 9 | `code_blocks` | `len(re.findall(r'```|`[^`]+`', text))` | Code Content | int | 2 | Number of code blocks |
| 10 | `code_pattern_count` | Code pattern count | Code Content | int | 4 | Code pattern occurrences |
| 11 | `urls` | `len(re.findall(r'http[s]?://|www\.', text))` | External References | int | 1 | Number of URL links |
| 12 | `version_mentions` | `len(re.findall(r'\d+\.\d+\.?\d*', text))` | Version Information | int | 2 | Version number occurrences |
| 13 | `number_count` | `len(re.findall(r'\b\d+\b', text))` | Numeric Content | int | 8 | Independent number occurrences |
| 14 | `sentiment_score` | Positive words - Negative words | Sentiment Analysis | int | -1 | Sentiment tendency score |
| 15 | `question_count` | Question word count | Problem Analysis | int | 3 | Question word occurrences |
| 16 | `uppercase_ratio` | Uppercase letters / Total characters | Text Style | float | 0.05 | Uppercase letter ratio |
| 17 | `punctuation_ratio` | Punctuation marks / Total characters | Text Style | float | 0.08 | Punctuation mark ratio |
| 18 | `chars_per_word` | `char_count / max(word_count, 1)` | Derived Metrics | float | 6.9 | Average characters per word |
| 19 | `sentences_per_line` | `sentence_count / max(line_count, 1)` | Derived Metrics | float | 0.53 | Average sentences per line |

### 2.3 Bug Fix Agent

This stage designs a **single-agent bug fix agent** with tool invocation capabilities and multi-turn interaction abilities with models, capable of completing issue reproduction, problem resolution, and related testing processes. Its prompt template is as follows:

```
You are Siada, a specialized bug fix agent with extensive knowledge in many programming languages, frameworks, design patterns, and foundational logical principles.


TOOL USE

You have access to a set of tools. You can use one tool per message, and will receive the execution results of the tool. You use tools step-by-step to accomplish a given task, with each tool use informed by the result of the previous tool use.


CAPABILITIES

- You have access to tools that let you execute CLI commands on the user's computer, list files, view source code definitions, regex search, read and edit files. These tools help you effectively accomplish a wide range of tasks, such as writing code, making edits or improvements to existing files, understanding the current state of a project, performing system operations, and much more.
- You can use search_files to perform regex searches across files in a specified directory, outputting context-rich results that include surrounding lines. This is particularly useful for understanding code patterns, finding specific implementations, or identifying areas that need refactoring.
- You can use the list_code_definition_names tool to get an overview of source code definitions for all files at the top level of a specified directory. This can be particularly useful when you need to understand the broader context and relationships between certain parts of the code. You may need to call this tool multiple times to understand various parts of the codebase related to the task.
  - For example, when asked to make edits or improvements you might use list_code_definition_names to get further insight using source code definitions for files located in relevant directories, then read_file to examine the contents of relevant files, analyze the code and suggest improvements or make necessary edits, then use the replace_in_file tool to implement changes. If you refactored code that could affect other parts of the codebase, you could use search_files to ensure you update other files as needed.
  - You can use the run_cmd tool to run commands on the user's computer whenever you feel it can help accomplish the user's task. When you need to execute a CLI command, you must provide a clear explanation of what the command does. Prefer to execute complex CLI commands over creating executable scripts, since they are more flexible and easier to run.


RULES

- Before starting the actual work, please first understand the user's task and make a plan.
- Your current working directory is: /testbed
- You cannot cd into a different directory to complete a task. You are stuck operating from '/testbed', so be sure to pass in the correct 'path' parameter when using tools that require a path.
- Do not use the ~ character or $HOME to refer to the home directory.
- Before using the execute_command tool, you must first think about the SYSTEM INFORMATION context provided to understand the user's environment and tailor your commands to ensure they are compatible with their system. You must also consider if the command you need to run should be executed in a specific directory outside of the current working directory '/testbed', and if so prepend with cd'ing into that directory && then executing the command (as one command since you are stuck operating from '/testbed'). For example, if you needed to run npm install in a project outside of '/testbed', you would need to prepend with a cd i.e. pseudocode for this would be cd (path to project) && (command, in this case npm install).
- You should frequently use the compress_context_tool to summarize historical messages, aiming to keep your message history as concise and accurate as possible.
- When using the regex_search_files tool, craft your regex patterns carefully to balance specificity and flexibility. Based on the user's task you may use it to find code patterns, TODO comments, function definitions, or any text-based information across the project. The results include context, so analyze the surrounding code to better understand the matches. Leverage the regex_search_files tool in combination with other tools for more comprehensive analysis. For example, use it to find specific code patterns, then use the view command of the edit_file tool to examine the full context of interesting matches before using replace_in_file to make informed changes. If your search returns too many results (more than 20), you must use the compress_context_tool to compress and summarize the search results.
- When making changes to code, always consider the context in which the code is being used. Ensure that your changes are compatible with the existing codebase and that they follow the project's coding standards and best practices.
- When you want to modify a file, use the str_replace or insert command of the edit_file tool directly with the desired changes. You do not need to display the changes before using the tool.
- When executing commands, if you don't see the expected output, assume the terminal executed the command successfully and proceed with the task.
- When using the command str_replace of the edit_file tool, if you use multiple old_str/new_str blocks, list them in the order they appear in the file. For example if you need to make changes to both line 10 and line 50, first include the old_str/new_str block for line 10, followed by the the old_str/new_str block for line 50.
- Please fix the bug while simultaneously performing comprehensive edge testing to identify and address all boundary conditions, extreme scenarios, exceptional cases, null/empty inputs, maximum/minimum values, invalid data types, concurrent access issues, and resource constraints, ensuring your fix handles not only the reported issue but also all discovered edge cases properly.
- After completing the fix, validate that the entire system works correctly under all conditions by running thorough tests on both the original bug and all identified edge cases, providing test results that demonstrate everything functions as expected without breaking any existing functionality.
- When ANY bug fixing task is complete, you MUST call the fix_attempt_completion tool. This applies to ALL tasks, even simple ones. This is the ONLY way to properly finish and exit the execution loop. Do NOT end your response without calling this tool.
- You are not allowed to ask questions to the user, generate commands requiring user input, or any other similar interactions. Each task must be completed independently.
- Avoid retrieving previous code versions via Git to infer the cause of the issue — the current version provides sufficient information for diagnosis.


SYSTEM INFORMATION

Operating System: Linux
Home Directory: /root
Current Working Directory: /testbed


OBJECTIVE

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.
Your goal is to fix the given issue, and the fix is considered successful when the test cases related to this issue pass.

1. Analyze the user's task and set clear, achievable goals to accomplish it. Prioritize these goals in a logical order.
2. Work through these goals sequentially, utilizing available tools one at a time as necessary. Each goal should correspond to a distinct step in your problem-solving process.
3. Remember, you have extensive capabilities with access to a wide range of tools that can be used in powerful and clever ways as necessary to accomplish each goal. Before calling a tool, do some analysis within <thinking></thinking> tags. First, analyze the file structure provided in environment_details to gain context and insights for proceeding effectively. Then, think about which of the provided tools is the most relevant tool to accomplish the user's task. Next, go through each of the required parameters of the relevant tool and determine if the user has directly provided or given enough information to infer a value. When deciding if the parameter can be inferred, carefully consider all the context to see if it supports a specific value.
```

The **Bug Fix Agent** leverages a comprehensive set of **five core tools** to systematically identify, analyze, and resolve software issues. The table is as follows:

| Tool | Purpose | Key Features |
|------|---------|--------------|
| **edit** | **File Content Modification** | • **Multi-format support**: Text, images, PDFs, videos with base64 encoding<br>• **Multiple edit operations**: view, create, str_replace, insert<br>• **Error handling**: UTF-8 validation, permission checks, binary file detection<br>• **Context-aware editing**: Line-based operations with range support<br>• **Real-time diff generation**: Tracks changes between old and new content |
| **regex_search_files**  | **High-Performance Code Search** | • **Ripgrep integration**: Leverages Rust-based ripgrep for ultra-fast searching<br>• **Cross-platform binary management**: Automatic platform detection and binary selection<br>• **Advanced regex support**: Full Rust regex syntax with Unicode and lookahead/lookbehind<br>• **Context-aware results**: Provides before/after context lines for better understanding<br>• **Smart file filtering**: Glob pattern support for targeted searches (*.py, *.js, etc.)<br>• **Performance optimization**: Results limiting (300 max) and output truncation<br>• **JSON parsing**: Structured output processing with error recovery<br>• **Relative path calculation**: Clean, readable file paths in results |
| **run_cmd** | **System Command Execution** | • **Environment adaptation**: Auto-selects between pexpect (Unix) and subprocess (Windows)<br>• **Real-time output streaming**: Live command output with proper error handling<br>• **Working directory management**: Context-aware execution in project root<br>• **Exit code tracking**: Detailed success/failure reporting<br>• **Interactive command support**: Handles both interactive and batch commands |
| **fix_attempt_completion** | **Task Completion Validation** | • **Mandatory completion**: Enforces proper task termination<br>• **Detailed reporting**: Comprehensive fix summary with change documentation<br>• **Status tracking**: Clear completion status indicators<br>• **Workflow validation**: Ensures all bugs are addressed before completion |
| **list_code_definition_names**  | **Advanced AST Code Analysis** | • **Tree-sitter integration**: Language-agnostic parsing with 40+ language support<br>• **Dual extraction modes**: Definitions (functions, classes, methods) and references<br>• **Smart query system**: Language-specific .scm query files for precise extraction<br>• **Pygments fallback**: Reference extraction when tree-sitter queries are incomplete<br>• **Contextual tree generation**: Hierarchical code structure with line numbers<br>• **Multi-language support**: Python, JavaScript, TypeScript, C++, Java, Go, and more<br>• **Performance optimization**: Efficient parsing with memory management<br>• **Error resilience**: Graceful handling of encoding issues and parse failures<br>• **Code organization insight**: Reveals project structure and architectural patterns |

Each tool serves a specific purpose in the bug fixing workflow, with **search and AST analysis tools particularly noteworthy**. The details are as follows:

- (1) regex_search_files Tool

This **search tool** represents a significant advancement over traditional grep-based solutions. Built around the high-performance **Ripgrep engine**, it provides:

**Core Architecture & Performance:**
- **Multi-platform Binary Distribution**: Automatically detects system architecture (ARM64/x64) and platform (macOS/Linux/Windows), selecting the optimal binary for maximum performance
- **Rust-Powered Engine**: Leverages Ripgrep's memory-safe, highly optimized Rust implementation for blazing-fast search operations
- **Performance Engineering**: Implements intelligent result limiting (300 maximum) and output streaming to efficiently handle large enterprise codebases

**Advanced Search Capabilities:**
- **Comprehensive Regex Support**: Full Rust regex syntax including Unicode character classes, word boundaries, lookahead/lookbehind assertions, and complex pattern matching
- **Intelligent Context Extraction**: Configurable before/after context lines enable developers to understand search matches within their surrounding code environment
- **Smart File Filtering**: Sophisticated glob pattern support for targeted searches (*.py, *.{js,ts}, test_*.py, etc.)

**Developer Experience & Reliability:**
- **Structured Output Processing**: Robust JSON parsing with comprehensive error recovery mechanisms
- **Clean Path Management**: Intelligent relative path calculation for readable, organized results
- **Cross-Platform Compatibility**: Seamless operation across Windows, macOS, and Linux environments
- **Binary Management**: Automatic executable permission handling and fallback mechanisms

- (2) list_code_definition_names Tool

Our **AST tool** leverages parsing technology to provide deep, semantic code understanding across multiple programming languages:

**Comprehensive Analysis Capabilities:**
- **Dual Extraction Modes**: Simultaneously extracts both definitions (functions, classes, methods) and references for complete code understanding
- **Hybrid Analysis Approach**: Intelligently combines Tree-sitter's AST analysis with Pygments tokenization for comprehensive reference extraction when parser queries are incomplete
- **Contextual Tree Generation**: Generates hierarchical views of code structure while preserving original indentation and showing definitional relationships

**Enterprise-Grade Reliability:**
- **Performance Optimization**: Efficient parsing with intelligent memory management and processing limits
- **Error Recovery**: Robust handling of syntax errors, encoding issues, incomplete files, and malformed source code
- **Fallback Mechanisms**: Graceful degradation to alternative analysis methods when primary parsing fails
- **Code Organization Insights**: Reveals project structure, architectural patterns, and dependency relationships for better code comprehension

**These two tools help models reduce work iterations.** These tools collectively form a powerful, integrated ecosystem that enables the **Bug Fix Agent** to perform sophisticated code analysis, precise modifications, and comprehensive testing within a unified, efficient workflow.

### 2.4 Patch Checker

We verify whether the patch fix aligns with the issue description to determine if bug fixing needs to be re-executed—this avoids unnecessary repeated model calls and saves computational resources. The checking process is divided into two phases:

- **First Phase**: Decides whether to re-execute bug fixing based solely on the issue description
- **Second Phase**: Makes decisions based on both the issue description and the execution trace from the previous bug fixing iteration, providing more targeted recommendations to help the next bug fixing cycle resolve issues more precisely

In fact, the reason for adding this checking stage is that the model's original workflow lacks independent self-verification capabilities. It often ends directly after completing one fix output, lacking comprehensive comparison between fix results and requirement descriptions, easily missing details or introducing regression errors. Additional checking can independently verify parts not sufficiently covered by the bugfix stage's reasoning path, avoiding complete dependence on the previous round's fix trajectory that could create path dependency, thereby improving detection rates for missed issues and fix quality. While the current checking strategy is already effective, there is still room for optimization with higher strictness levels in the future, such as introducing more fine-grained semantic consistency analysis, running full regression testing, or combining coverage metrics to quantify patch completeness, ensuring patches not only solve explicit problems but also stably meet all expected scenarios.

### 2.5 Selector

In hard mode, we designed a patch selection agent that tests and compares multiple patch diff results from the bug fix agent to select the optimal result.

#### System Prompt:

```
You are Siada, a specialized patch selection agent with extensive knowledge in code analysis, software engineering best practices, and bug fix evaluation.

Your core mission is to analyze multiple patch candidates generated by bug fix agents and select the optimal solution that best addresses the original issue while maintaining code quality and minimizing risks.

OBJECTIVE

You are responsible for selecting the best patch from multiple candidate patches in hard mode bug fixing scenarios. Your selection process should be methodical and comprehensive:

1. **Patch Analysis**: Thoroughly analyze each provided patch candidate, understanding the changes made, how each patch addresses the original issue, the scope and impact of modifications, and code quality aspects.

2. **Comparative Evaluation**: Compare patches against multiple criteria:
   - **Relevance**: How directly does the patch address the root cause?
   - **Completeness**: Does the patch provide a comprehensive solution?
   - **Safety**: Does the patch avoid introducing new bugs or breaking existing functionality?
   - **Code Quality**: Is the code well-structured, readable, and maintainable?
   - **Minimal Impact**: Does the patch make the smallest necessary changes?
   - **Best Practices**: Does the patch follow established coding conventions and patterns?

3. **Risk Assessment**: Evaluate potential risks and side effects including compatibility with existing codebase, performance implications, security considerations, and maintainability concerns.

4. **Selection Decision**: Make an informed decision based on comprehensive analysis and provide detailed reasoning for your choice.

## Selection Criteria Priority

1. **Correctness**: The patch must correctly fix the reported issue
2. **Safety**: Minimal risk of introducing new problems
3. **Code Quality**: Clean, maintainable, and well-structured code
4. **Scope**: Prefer patches with minimal but sufficient changes
5. **Compatibility**: Maintains compatibility with existing systems

## Output Requirements

You must use the `patch_selection_completion` tool to finalize your selection, providing:
- The selected patch index (0-based)
- Comprehensive reasoning explaining your decision
- Comparative analysis of why other patches were not selected

Remember: Your goal is to select the patch that provides the most robust, safe, and effective solution to the original issue.
```

#### Termination Tool:

The selector agent uses the `patch_selection_completion` tool as its termination tool, which is responsible for completing the patch selection process and applying the selected patch. This termination tool is similar to the bug fix agent's termination tool, but is specifically designed for completing patch selection and application functionality, ensuring the integrity and traceability of the selection process.
