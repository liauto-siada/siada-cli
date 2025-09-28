from openai.types.chat import ChatCompletionMessageParam
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from siada.agent_hub.coder.tracing.bug_fix_trace_collector import BugFixTraceCollector

from siada.foundation.setting import settings
from siada.foundation.tools.json_util import get_json_content
from siada.provider.client_factory import get_client_with_kwargs


class PsFrComparator:
    @staticmethod
    async def compare(problem_statement: str, patch: str, context:any, trace_collector: Optional["BugFixTraceCollector"] = None) -> dict:
        """
        Compare the PS data with the FR data and return discrepancies.
        """
        try:
            patch_summary_prompt = PsFrComparator.build_get_summary_prompt(patch)
            patch_summary = await PsFrComparator.get_patch_summary(patch, context)
            
            comparison_prompt = PsFrComparator.build_compare_prompt(problem_statement, patch_summary)
            compare_result = await PsFrComparator.get_compare_result(problem_statement, patch_summary, context)
            
            # Record trace
            if trace_collector:
                trace_collector.record_compare_trace(
                    patch_summary_prompt=patch_summary_prompt,
                    patch_content=patch,
                    patch_summary=patch_summary,
                    comparison_prompt=comparison_prompt,
                    problem_statement=problem_statement,
                    comparison_result=compare_result
                )
            
            return compare_result
            
        except Exception as e:
            error_result = {
                "is_covered": False,
                "reason": f"Error in comparison process: {str(e)}"
            }
            
            # Record error trace
            if trace_collector:
                patch_summary_prompt = PsFrComparator.build_get_summary_prompt(patch)
                comparison_prompt = PsFrComparator.build_compare_prompt(problem_statement, "")
                trace_collector.record_compare_trace(
                    patch_summary_prompt=patch_summary_prompt,
                    patch_content=patch,
                    patch_summary=f"Error: {str(e)}",
                    comparison_prompt=comparison_prompt,
                    problem_statement=problem_statement,
                    comparison_result=error_result
                )
            
            return error_result


    @staticmethod
    async def get_compare_result(problem_statement: str, patch_summary: str, context:any) -> dict:

        prompt = PsFrComparator.build_compare_prompt(problem_statement, patch_summary)
        print(f"compare ps fr prompt: {prompt}")
        response = await PsFrComparator.call_llm(prompt, context)

        if response and response.choices and response.choices[0].message:
            compare_result = response.choices[0].message.content
            if compare_result:
                try:
                    parsed_json = get_json_content(compare_result)
                    return parsed_json
                except Exception as e:
                    print(f"Compare get json failed: {e}.")
                    print(f"Raw compare_result content: {compare_result}")
                    raise Exception(f"JSON parsing failed: {e}")


        raise Exception("cannot get compare result from model response")


    @staticmethod
    async def get_patch_summary(patch: str, context:any) -> str:
        """
        Generate a summary of the patch changes.
        """
        summary_prompt = PsFrComparator.build_get_summary_prompt(patch)

        response = await PsFrComparator.call_llm(summary_prompt, context)

        if response and response.choices and response.choices[0].message:
            summary = response.choices[0].message.content
            if summary:
                return summary.strip()

        raise Exception("cannot get get_patch_summary from model response")

    @staticmethod
    async def call_llm(user_task, context):
        model_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": user_task},
        ]
        # Call the model
        default_kwargs = {
            "model": settings.Claude_4_0_SONNET,
            "messages": model_messages,
            "stream": False,
            "temperature": 0.1,  # Lower temperature for accuracy and consistency
        }
        # Use get_client_with_kwargs to support context parameter overrides
        client, complete_kwargs = get_client_with_kwargs(context, default_kwargs)
        response = await client.completion(**complete_kwargs)
        return response

    @staticmethod
    def build_compare_prompt(problem_statement: str, fix_summary: str):

        prompt = f"""Compare the differences between the **technical implementation** described in the fix summary and the original problem description, and analyze whether the fix summary **fully** covers the problem description.
Focus **only** on the technical implementation part. Do **not** overlook any technical details. Treat **any** difference or omission of technical details as a failure to cover the problem. You must explicitly state whether the fix summary covers the problem description; for any case that does **not**, provide the reasons.


## Required Output Fields:
1. **is_covered**: true/false (true if the fix summary fully covers the problem description, otherwise false)
2. **reason**: If the fix summary fully covers the problem description, return an empty string here. Otherwise, provide detailed reasons explaining why it does not cover the problem description.

IMPORTANT: Return ONLY the JSON response. Do not include any explanatory text, analysis, or comments before or after the JSON.


## **Required JSON Output Format**
Your response must be ONLY valid JSON in exactly this format with no additional text:

```json
{{
  "is_covered": true,
  "reason": "If the fix summary fully covers the problem description, return an empty string here. Otherwise, provide detailed reasons explaining why it does not cover the problem description."
}}
```
---

## Fix Summary
{fix_summary}

---
     
##Problem  Description
{problem_statement}
"""

        return prompt

    @staticmethod
    def build_get_summary_prompt(patch: str):

        prompt = f"""Summarize the content of this patch change:
            
        Patch:
        {patch}
        """
        return prompt.strip()
