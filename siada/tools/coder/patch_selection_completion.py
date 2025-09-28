from agents import RunContextWrapper, function_tool

from siada.foundation.code_agent_context import CodeAgentContext


PATCH_SELECTION_COMPLETION_DOCS = f"""Patch Selection Completion Tool

This tool is called when completing a patch selection process. It captures the final selection of the optimal patch from multiple candidate patches.

Parameters:
- selected_patch_index (int): The selected patch index starting from 0. This indicates which patch among the candidates has been chosen as the optimal solution.
- reasoning (str): Detailed analysis summary explaining the patch selection decision. Must include:
   - Detailed selection reasoning explaining why this patch is optimal
   - Comparison analysis between different patch candidates
   - Technical assessment of the selected patch's quality and effectiveness
   - Risk assessment and potential impact evaluation
   - Justification for why other patches were not selected

"""


@function_tool(
    name_override="patch_selection_completion", description_override=PATCH_SELECTION_COMPLETION_DOCS, failure_error_function=None
)
async def patch_selection_completion(context: RunContextWrapper[CodeAgentContext], selected_patch_index: int,
                                   reasoning: str) -> dict:
    return {
        "selected_patch_index": selected_patch_index,
        "reasoning": reasoning
    }
