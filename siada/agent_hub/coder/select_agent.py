import ast
import subprocess
import tempfile
import os
from typing import List, Optional, TYPE_CHECKING

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.issue_review_agent import IssueReviewAgent
from siada.foundation.code_agent_context import CodeAgentContext

if TYPE_CHECKING:
    from siada.agent_hub.coder.tracing.bug_fix_trace_collector import BugFixTraceCollector


class SelectAgent(CodeGenAgent):
    """
    Agent for selecting the best patch from available candidates
    """
    
    def __init__(self, *args, **kwargs):
        self.issue_review_agent = IssueReviewAgent()
        super().__init__(
            name="SelectAgent",
            tools=[],  # SelectAgent doesn't need additional tools
            *args,
            **kwargs,
        )

    async def select_and_apply_best_patch(
        self,
        user_input: str,
        context: CodeAgentContext,
        patch_list: List[str],
        trace_collector: Optional["BugFixTraceCollector"] = None
    ) -> bool:
        """
        Select and apply the optimal patch for final fix
        
        Args:
            user_input: User input problem description
            context: Code agent context
            patch_list: List of available patches
            trace_collector: Optional trace collector for recording selection process
            
        Returns:
            bool: True if patch was successfully applied, False otherwise
        """
        if not patch_list:
            print("No patches available for selection")
            return False
            
        print(f"Starting optimal patch selection from {len(patch_list)} available patches...")
        
        patch_selection_prompt = self._build_patch_selection_prompt(user_input, patch_list)
        
        if trace_collector:
            trace_collector.start_patch_selection(patch_list, patch_selection_prompt)
        
        try:
            # Run selection agent
            selection_result = await self.issue_review_agent.run(
                patch_selection_prompt, context
            )
            
            # Parse selection result
            selection_output = ast.literal_eval(selection_result.final_output)
            selected_patch_index = selection_output.get("selected_patch_index", 0)
            reasoning = selection_output.get("reasoning", "No selection reasoning provided")
            
            print(f"Selected patch #{selected_patch_index + 1}")
            print(f"Selection reasoning: {reasoning}")
            
            # Apply selected patch
            success = False
            if 0 <= selected_patch_index < len(patch_list):
                selected_patch = patch_list[selected_patch_index]
                success = await self._apply_selected_patch(selected_patch, context)
            else:
                print("Invalid patch index selected, applying first patch as fallback")
                if patch_list:
                    selected_patch_index = 0
                    success = await self._apply_selected_patch(patch_list[0], context)
            
            if trace_collector:
                trace_collector.end_patch_selection(
                    selected_patch_index=selected_patch_index,
                    reasoning=reasoning,
                    application_success=success
                )
            
            return success
                    
        except Exception as e:
            print(f"Error occurred during patch selection: {e}")
            print("Using first patch as fallback solution")
            
            success = False
            reasoning = f"Error occurred during selection: {str(e)}, using fallback"
            
            if patch_list:
                success = await self._apply_selected_patch(patch_list[0], context)
            
            if trace_collector:
                trace_collector.end_patch_selection(
                    selected_patch_index=0 if patch_list else -1,
                    reasoning=reasoning,
                    application_success=success
                )
            
            return success

    def _build_patch_selection_prompt(self, user_input: str, patch_list: List[str]) -> str:
        """
        Build patch selection prompt information
        
        Args:
            user_input: User input problem description
            patch_list: Available patch list
            
        Returns:
            Prompt text for selecting optimal patch
        """
        prompt = f"""## 🎯 Patch Selection Task

**Original Issue:**
{user_input}

**Available Patch List:**
"""
        
        for i, patch in enumerate(patch_list):
            prompt += f"""
### Patch {i + 1}:
```diff
{patch}
```
"""
        
        prompt += f"""

## 📋 Task Requirements
Please select the most suitable patch from the above {len(patch_list)} patches to solve the original issue.

## 🔍 Evaluation Criteria
1. **Relevance**: Does the patch directly address the original issue?
2. **Completeness**: Does the patch provide a complete solution?
3. **Safety**: Does the patch avoid introducing new problems?
4. **Code Quality**: What is the code quality and maintainability of the patch?

## 📤 Output Format
Please return a Python dictionary in the following format:
```python
{{
    "selected_patch_index": <selected patch index starting from 0>,
    "reasoning": "<detailed selection reasoning explaining why this patch is optimal>"
}}
```

Please carefully analyze each patch and select the optimal solution.
"""
        return prompt

    async def _apply_selected_patch(self, patch: str, context: CodeAgentContext) -> bool:
        """
        Apply the selected patch
        
        Args:
            patch: Patch content to apply
            context: Code agent context
            
        Returns:
            bool: True if patch was successfully applied, False otherwise
        """
        try:
            # Use git apply or other methods to apply the patch
            # Since this is a diff format patch, we can use git apply
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as temp_file:
                temp_file.write(patch)
                temp_file_path = temp_file.name
            
            try:
                # Switch to project root directory
                original_cwd = os.getcwd()
                os.chdir(context.root_dir)
                
                print("🧹 Clearing working directory changes...")
                reset_result = subprocess.run(
                    ['git', 'reset', '--hard', 'HEAD'],
                    capture_output=True,
                    text=True
                )
                
                if reset_result.returncode == 0:
                    print("Working directory cleared successfully")
                else:
                    print(f"Failed to clear working directory: {reset_result.stderr}")
                
                # Use git apply to apply the patch
                result = subprocess.run(
                    ['git', 'apply', '--ignore-space-change', '--ignore-whitespace', temp_file_path],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print("Patch applied successfully")
                    return True
                else:
                    print(f"Patch application failed: {result.stderr}")
                    print("Trying alternative application methods...")
                    return False
                    
            finally:
                os.chdir(original_cwd)
                os.unlink(temp_file_path)
                
        except Exception as e:
            print(f"Error occurred while applying patch: {e}")
            return False
