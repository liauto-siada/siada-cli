from typing import Any, Optional, TYPE_CHECKING

from openai.types.chat import ChatCompletionMessageParam

if TYPE_CHECKING:
    from siada.agent_hub.coder.tracing.bug_fix_trace_collector import BugFixTraceCollector

from siada.foundation.config import settings
from siada.provider.client_factory import get_client_with_kwargs


class BugDescOptimizer:
    """
    A class to optimize bug descriptions.
    """

   # "project_type": "web_framework|data_visualization|data_science|development_tools|core_libraries",
    async def optimize(self, description: str, context: Any, project_type: str, trace_collector: Optional["BugFixTraceCollector"] = None) -> str:
        if project_type == "core_libraries" or project_type == "development_tools" :
            print("Optimizer: Infrastructure library") 
            opt_prompt = self.get_prompt_infrastructure_libraries(description)
        elif project_type == "data_visualization" or project_type == "data_science" : 
            print("Optimizer: Data library")
            opt_prompt = self.get_prompt_data_libibrary(description)
        else :
            print("Other library ")
            return description
      
        print(f"Optimizer prompt:{opt_prompt}")
        model_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": opt_prompt},
        ]

        default_kwargs = {
            "model": settings.Claude_4_0_SONNET,
            "messages": model_messages,
            "stream": False,
            "temperature": 0.2, 
        }

        # Use get_client_with_kwargs to support context parameter overrides
        client, complete_kwargs = get_client_with_kwargs(context, default_kwargs)
        response = await client.completion(**complete_kwargs)

        if response and response.choices and response.choices[0].message:
            opt_desc = response.choices[0].message.content
            if opt_desc:
                optimized_result = opt_desc.strip()
                
                self._record_optimization_trace(trace_collector, description, opt_prompt, optimized_result, project_type)
                
                return optimized_result

        raise Exception("cannot get analysis result from model response")

    def get_prompt_infrastructure_libraries_2(self, description)-> str:
        # psf 3/6  sphinx 9/16  other 9/24 _psf_sphinx_other_2

        return f"""Please analyze the following bug description and generate a more **complete** and **precise** bug report so that developers can fully understand and fix the issue.

### Optimization Requirements

1. **Identify Main Issue and All Potential Issues**

    * Do not only focus on the explicit error mentioned by the user, but also identify root causes that may lead to the error
    * Analyze technical details exposed in the error message
    * Analyze edge scenarios that may lead to the issues.

2. **Clarify Test Scenarios**

    * Define test scenarios for potential issues and ensure that all issues are covered by the test scenarios.

3. **Define Expected Behavior**

    * Clearly describe how different input formats should be handled
    * Require not only error recovery but also correct handling of all reasonable inputs

4. **Provide Complete Reproduction Steps**

    * Include specific, runnable code examples
    * Cover multiple data format scenarios

5. **Define Success Criteria**

---

### Principles

1. You can reorganize or expand the original problem description, but **do not delete** the content of the original problem description
2. Keep the technical information in the original problem description in their **original form**, including but not limited to source codes, test cases, stacks, environment information, and version information.

---

### Output Format

Generate a **structured bug report** that includes:

* **Issue Overview**
* **Detailed Problem Description** (including root cause)
* **Reproduction Steps** (with multiple scenarios)
* **Expected Behavior**
* **Acceptance Criteria**

---
### Here is the original bug description:

{description}
"""
    
    def _record_optimization_trace(
        self, 
        trace_collector: Optional["BugFixTraceCollector"], 
        description: str, 
        opt_prompt: str, 
        optimized_result: str, 
        project_type: str
    ) -> None:
        """
        Record optimization trace information
        
        Args:
            trace_collector: Optional trace collector
            description: Original description
            opt_prompt: Optimization prompt used
            optimized_result: Optimized result
            project_type: Project type
        """
        if not trace_collector:
            return
            
        trace_collector.record_optimization(
            prompt=opt_prompt,
            original_input=description,
            optimized_result=optimized_result,
            project_type=project_type
        )

    def get_prompt_data_libibrary(self, description) -> str:
        #3 matplotlib 13/17  scikit-learn:14/19
        return f"""
Please analyze the following bug description and generate a more **complete** and **precise** bug report so that developers can fully understand and fix the issue.

### Optimization Requirements

1. **Identify Main Issue and All Potential Issues**
    Adopt a layered exhaustive strategy:
        * **At the code implementation level**, systematically check all technical aspects, including algorithm logic, data structure selection, boundary conditions, exception handling, state management, and memory management.
        * **At the interface design level**, analyze design flaws such as parameter validation, return value definitions, side-effect control, error messages, and compatibility.
        * **At the business logic level**, review requirement understanding, test case coverage, edge scenarios, and user expectations.
    Apply a **matrix analysis method** to build a three-dimensional matrix of *issue type × trigger condition × impact scope*, ensuring every combination is considered.
    Adopt **contradictory thinking**, reasoning in reverse from the perspective of “why did it not fail?” to identify the protection mechanisms that should exist.
    Use **analogy expansion**, comparing with similar functionalities implemented in standard libraries or open-source projects to recognize missing safeguards.
    Apply a **scenario enumeration method** to list all possible input combinations, operation sequences, and concurrency situations, in order to uncover overlooked test scenarios.

2. **Clarify Test Scenarios**
   * First, classify the cases by issue type (core issues, boundary conditions, regression tests, performance impact) and modification type (deletion, addition, modification). 
   * Then, consider different data scales, types, and characteristics from the input data dimension, as well as the timing of operations (before, during, and after iterations). 
   * Each test scenario should clearly specify four elements: preconditions (initial state), operation steps (specific execution), expected results (intended behavior), and verification method (how to confirm). 
   * At the same time, establish a prioritization system: P0 covers core bug reproduction, P1 tests common variants, P2 handles edge cases, and P3 validates performance compatibility. 
   * Finally, use a test matrix to ensure that all important combinations are covered, avoiding the omission of critical scenarios and thereby ensuring the completeness and effectiveness of testing.

3. **Define Expected Behavior**
   * Clearly describe how different input formats should be handled
   * Require not only error recovery but also correct handling of all reasonable inputs

4. **Provide Complete Reproduction Steps**
   * Include specific, runnable code examples
   * Cover multiple data format scenarios

5. **Define Success Criteria**
   * List all conditions that must be satisfied after the fix
   * Ensure both error recovery and data compatibility are included
---

### Principles
1. Do not omit or alter any information from the original bug description.
---

### Output Format

Generate a **structured bug report** named Initial Analysis Report that and includes:

* **Issue Overview**
* **Detailed Problem Description** (including root cause)
* **Reproduction Steps** (with multiple scenarios)
* **Expected Behavior**
* **Acceptance Criteria**

---
### Here is the original bug description:

{description}
"""

    def get_prompt_infrastructure_libraries(self, description):
        #1. pytest 8/17, sympy 39/77

        return f"""Please analyze the following bug description and generate a more **complete** and **precise** bug report so that developers can fully understand and fix the issue.

### Optimization Requirements

1. **Identify All Potential Issues**

   * Do not only focus on the explicit error mentioned by the user, but also identify root causes that may lead to the error
   * Analyze technical details exposed in the error message

2. **Clarify Test Scenarios**

3. **Define Expected Behavior**

   * Clearly describe how different input formats should be handled
   * Require not only error recovery but also correct handling of all reasonable inputs

4. **Provide Complete Reproduction Steps**

   * Include specific, runnable code examples
   * Cover multiple data format scenarios

5. **Define Success Criteria**

   * List all conditions that must be satisfied after the fix
   * Ensure both error recovery and data compatibility are included

---

### Principles

1. Do not omit or alter any information from the original bug description.

---

### Output Format

Generate a **structured bug report** that includes:

* **Issue Overview**
* **Detailed Problem Description** (including root cause)
* **Reproduction Steps** (with multiple scenarios)
* **Expected Behavior**
* **Acceptance Criteria**

---
### Here is the original bug description:

{description}
"""

class LessOriginBugDescOptimizer(BugDescOptimizer):
    """
    A class to optimize bug descriptions with less restrictive prompt from version d32cbdebcc54447e36e410aa4bf4ed18c722a8d2.
    """

    def get_prompt(self, description):
        return f"""
Please analyze the following bug description and generate a more **complete** and **precise** bug report so that developers can fully understand and fix the issue.

### Optimization Requirements

1. **Identify All Potential Issues**

   * Do not only focus on the explicit error mentioned by the user, but also identify root causes that may lead to the error
   * Analyze technical details exposed in the error message
   * Analyze edge scenarios that may lead to the issues.

2. **Clarify Test Scenarios**

   * Define test scenarios for potential issues and ensure that all issues are covered by the test scenarios.

3. **Define Expected Behavior**

   * Clearly describe how different input formats should be handled
   * Require not only error recovery but also correct handling of all reasonable inputs

4. **Provide Complete Reproduction Steps**

   * Include specific, runnable code examples
   * Cover multiple data format scenarios

5. **Define Success Criteria**

   * List all conditions that must be satisfied after the fix
   * Ensure both error recovery and data compatibility are included

---

### Principles

1. **Do not delete** the content of the original problem description
2. Keep the technical information in the original problem description in their **original form**, including but not limited to source codes, test cases, stacks, environment information, and version information.

---

### Output Format

Generate a **structured bug report** that includes:

* **Issue Overview**
* **Detailed Problem Description** (including root cause)
* **Reproduction Steps** (with multiple scenarios)
* **Expected Behavior**
* **Acceptance Criteria**

---


{description}
"""
