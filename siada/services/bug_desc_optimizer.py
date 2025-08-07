from typing import Any, Optional, TYPE_CHECKING

from openai.types.chat import ChatCompletionMessageParam

if TYPE_CHECKING:
    from siada.agent_hub.coder.tracing.bug_fix_trace_collector import BugFixTraceCollector

from siada.foundation.setting import settings
from siada.provider.client_factory import get_client_with_kwargs


class BugDescOptimizer:
    """
    A class to optimize bug descriptions.
    """

   # "project_type": "web_framework|data_visualization|data_science|development_tools|core_libraries",
    async def optimize(self, description: str, context: Any, project_type: str='', trace_collector: Optional["BugFixTraceCollector"] = None) -> str:
        # if project_type != "web_framework":
        #     print("Optimizer: base optimizer ")
        #     opt_prompt = self.get_prompt_infrastructure_libraries(description)
        # else :
        #     print("Other library ")
        #     return description

        print("Optimizer: optimize bug description")
        opt_prompt = self.get_prompt_infrastructure_libraries(description)
      
        print(f"Optimizer prompt:{opt_prompt}")
        model_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": opt_prompt},
        ]

        default_kwargs = {
            "model": settings.Claude_4_0_SONNET,
            "messages": model_messages,
            "stream": False,
            "temperature": 0.01,
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

    def get_prompt_infrastructure_libraries(self, description):

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
