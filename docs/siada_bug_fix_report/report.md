*(This technical report is applicable to Siada-CLI v1.2.0)*

## 1. Introduction

**Siada CLI** is an open-source command-line AI workflow tool that provides professional intelligent agents for code development, debugging, and automation tasks. Among these, the **Code Generation Agent** serves as the starting point for all agents within Siada CLI. We believe that code generation based on large language models has the potential to empower every stage of the software engineering lifecycle. Based on this belief, we have conducted internal practice at **Li Auto** and open-sourced some of the capabilities within Siada CLI.

This report demonstrates how we applied Siada CLI to automatically resolve issues in the **SWE-bench-Lite benchmark**. Unlike many existing approaches that indiscriminately attempt to solve an issue multiple times, Siada CLI adopts a **"three-stage" process**—**issue description optimization, bug fixing (including issue reproduction, resolution, and related testing), and patch checking**—to complete issue resolution with minimal model calls and cost.
On the SWE-bench-Lite benchmark, Siada CLI achieved a **57.67% issue resolution rate (173/300)**, **ranking third among all models**. The following sections will introduce the system design and experimental results of the bug fix agent in Siada CLI.
![Siada CLI Leaderboard](leadboard.png)

## 2. System Overview
### 2.1 **Bug Fix of Siada CLI: A Three-Stage, Single-Agent System Design**

In the initial phase, we designed a **multi-agent architecture** based on human engineering bug fixing processes and **TDD (Test-Driven Development)** principles. This included an **issue reproduction agent**, **bug fix agent**, **test case agent**, and others, organized into a specific issue resolution workflow. Although we continuously attempted to optimize these agents, the multi-agent combination approach did not achieve ideal results in the bug fixing domain. We believe the main reasons are:

- **Model capability is sufficiently strong**: Current large language models can directly execute the closed-loop tasks of reproduction, localization, fixing, and testing within a single session. Additional issue reproduction agents and test agents do not provide more incremental content to the bug fix agent.
- **Models still have significant deficiencies in agent switching**: After trying fixed workflows (reproduction → fixing → testing), we attempted to let models autonomously switch agents and decide when to use specific agents. However, the actual effect showed that models currently struggle to perfectly implement such capabilities. Although frameworks like **openai-agent-sdk** and **adk** provide agent switching capabilities, we still believe current model capabilities cannot perfectly handle multi-agent tasks.
- **Single agent is more efficient**: Multi-agent approaches did not improve effectiveness but significantly reduced efficiency and increased costs.
- **Single agent provides flexible adaptive testing**: During the fixing process, new test cases can be dynamically generated and executed more strategically.

However, the single-agent mode alone was insufficient to achieve outstanding results. Therefore, we designed an alternative approach by adding **issue description optimization** and **patch checking** stages before and after the bug fix agent. The inspiration for these two stages comes from:

1. **Regarding issue description optimization**: As widely known, challengers more easily achieve high scores on the **swe-bench-verified** leaderboard. An important reason for this phenomenon is that the issue descriptions in verified cases are manually annotated. Therefore, we wondered whether we could have models automatically "annotate" issue descriptions.

2. **Regarding patch checking**: Based on previous multi-agent experiments, we found that if subsequent agents continue the work of preceding agents, they must trust the preceding agents' work to some extent, which creates "inertial thinking." If the preceding agent has problems, all subsequent work becomes meaningless (this is also one of the reasons why fixed-workflow multi-agent approaches perform poorly). Therefore, we believe there needs to be someone standing in opposition to the bug fix agent, forgetting the bug fix agent's work process, and then reviewing its fix results. Hence, we added the patch checking stage.

Therefore, the complete three stages are: **Issue Description Optimization → Bug Fixing → Patch Checking**.

The design of these three stages will be introduced in sections 2.2, 2.3, and 2.4 respectively.

## 2.2 Issue Description Optimization Stage

To reduce the negative impact of ambiguous task descriptions, we propose an **issue description optimizer**. It directly receives the original issue description and generates more complete and precise structured bug reports based on preset prompt templates.

### (1) Specific Optimization Content

The optimizer performs multi-dimensional enhancement of the original description:

- **Potential Issue Identification**: Not only focuses on explicit errors, but also infers potential root causes and analyzes technical details in error messages.
- **Test Scenario Clarification**: Lists various input forms and boundary conditions to ensure comprehensive test coverage.
- **Expected Behavior Definition**: Clearly defines how the system should correctly handle different inputs, rather than merely preventing errors.
- **Complete Reproduction Steps**: Provides directly executable code examples covering multiple data formats.
- **Acceptance Criteria Formulation**: Quantifies conditions for successful fixes, such as all related tests passing, maintaining backward compatibility, and meeting mathematical/business specifications.

### (2) Guidance Role for Models

- **Eliminating Ambiguity**: Transforms vague descriptions into clear "reproduce → fix → verify" closed-loop plans, reducing exploratory model calls.
- **Reducing Inference Bias**: Structured information helps models focus on actual root causes rather than surface phenomena.
- **Improving Fix Completeness**: Unified acceptance criteria promote generated solutions that cover all boundary conditions, avoiding incomplete fixes.
- **Enhancing Generalization**: The standardized analysis framework facilitates transfer fixing for similar issues.

### (3) Case Analysis

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

## 2.3 Bug Fixing Stage

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


The **Bug Fix Agent** leverages a comprehensive set of **five core tools** to systematically identify, analyze, and resolve software issues. The tbale is as follows：
| Tool | Purpose | Key Features |
|------|---------|--------------|
| **edit** | **File Content Modification** | • **Multi-format support**: Text, images, PDFs, videos with base64 encoding<br>• **Multiple edit operations**: view, create, str_replace, insert<br>• **Error handling**: UTF-8 validation, permission checks, binary file detection<br>• **Context-aware editing**: Line-based operations with range support<br>• **Real-time diff generation**: Tracks changes between old and new content |
| **regex_search_files** <br>*(Self-developed)* | **High-Performance Code Search** | • **Ripgrep integration**: Leverages Rust-based ripgrep for ultra-fast searching<br>• **Cross-platform binary management**: Automatic platform detection and binary selection<br>• **Advanced regex support**: Full Rust regex syntax with Unicode and lookahead/lookbehind<br>• **Context-aware results**: Provides before/after context lines for better understanding<br>• **Smart file filtering**: Glob pattern support for targeted searches (*.py, *.js, etc.)<br>• **Performance optimization**: Results limiting (300 max) and output truncation<br>• **JSON parsing**: Structured output processing with error recovery<br>• **Relative path calculation**: Clean, readable file paths in results |
| **run_cmd** | **System Command Execution** | • **Environment adaptation**: Auto-selects between pexpect (Unix) and subprocess (Windows)<br>• **Real-time output streaming**: Live command output with proper error handling<br>• **Working directory management**: Context-aware execution in project root<br>• **Exit code tracking**: Detailed success/failure reporting<br>• **Interactive command support**: Handles both interactive and batch commands |
| **fix_attempt_completion** | **Task Completion Validation** | • **Mandatory completion**: Enforces proper task termination<br>• **Detailed reporting**: Comprehensive fix summary with change documentation<br>• **Status tracking**: Clear completion status indicators<br>• **Workflow validation**: Ensures all bugs are addressed before completion |
| **list_code_definition_names** <br>*(Self-developed)* | **Advanced AST Code Analysis** | • **Tree-sitter integration**: Language-agnostic parsing with 40+ language support<br>• **Dual extraction modes**: Definitions (functions, classes, methods) and references<br>• **Smart query system**: Language-specific .scm query files for precise extraction<br>• **Pygments fallback**: Reference extraction when tree-sitter queries are incomplete<br>• **Contextual tree generation**: Hierarchical code structure with line numbers<br>• **Multi-language support**: Python, JavaScript, TypeScript, C++, Java, Go, and more<br>• **Performance optimization**: Efficient parsing with memory management<br>• **Error resilience**: Graceful handling of encoding issues and parse failures<br>• **Code organization insight**: Reveals project structure and architectural patterns |

Each tool serves a specific purpose in the bug fixing workflow, with **search and AST analysis tools particularly noteworthy**. The details are as follows:

### (1) regex_search_files Tool

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

### (2) list_code_definition_names Tool

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


## 2.4 Patch Checking Stage

We verify whether the patch fix aligns with the issue description to determine if bug fixing needs to be re-executed—this avoids unnecessary repeated model calls and saves computational resources. The checking process is divided into two phases:

- **First Phase**: Decides whether to re-execute bug fixing based solely on the issue description
- **Second Phase**: Makes decisions based on both the issue description and the execution trace from the previous bug fixing iteration, providing more targeted recommendations to help the next bug fixing cycle resolve issues more precisely

In fact, the reason for adding this checking stage is that the model's original workflow lacks independent self-verification capabilities. It often ends directly after completing one fix output, lacking comprehensive comparison between fix results and requirement descriptions, easily missing details or introducing regression errors. Additional checking can independently verify parts not sufficiently covered by the bugfix stage's reasoning path, avoiding complete dependence on the previous round's fix trajectory that could create path dependency, thereby improving detection rates for missed issues and fix quality. While the current checking strategy is already effective, there is still room for optimization with higher strictness levels in the future, such as introducing more fine-grained semantic consistency analysis, running full regression testing, or combining coverage metrics to quantify patch completeness, ensuring patches not only solve explicit problems but also stably meet all expected scenarios.

## 2.5 Future TODO

We believe we have not fully maximized the potential of the "Bug Description Optimization" and "Patch Checking" stages. Their ceiling is far beyond this, and we will continue to optimize these two stages using more methods in the future, such as adjusting the strictness level of patch checking. Please stay tuned.

---

