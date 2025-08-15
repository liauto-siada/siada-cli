"""
Fix Result Checker - 通过模型判断代码修复是否真正解决了问题
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, Union

from openai.types.chat import ChatCompletionMessageParam

from siada.provider.client_factory import get_client_with_kwargs
from siada.foundation.config import settings

logger = logging.getLogger(__name__)

class FixResultChecker:
    """修复结果检查器
    
    使用模型分析代码修复是否真正解决了描述的问题
    """
    async def check(self, issue_desc: str, fix_code: str, context: Any) -> Dict[str, Any]:
        """检查修复代码是否真正解决了问题
        
        Args:
            issue_desc: 问题描述
            fix_code: 修复代码
            context: 上下文对象，包含provider等信息
            
        Returns:
            Dict[str, Any]: 包含检查结果的字典
            {
                "is_fixed": bool,      # 是否修复（部分修复算作未修复）
                "check_summary": str,  # 检查摘要，说明修复状态和原因
                "analysis": str        # 完整的分析过程
            }
        """
        try:
            analysis_result = await self._call_model_for_analysis(issue_desc, fix_code, context)
            return self._parse_analysis_result(analysis_result)
        except Exception as e:
            logger.error(f"Fix result check failed: {e}", exc_info=True)
            return {
                "is_fixed": False,
                "check_summary": f"分析过程中发生错误: {str(e)}",
                "analysis": f"错误详情: {str(e)}"
            }
    
    async def _call_model_for_analysis(self, issue_desc: str, fix_code: str, context: Any) -> str:
        """调用模型进行分析
        
        Args:
            issue_desc: 问题描述
            fix_code: 修复代码
            context: 上下文对象，包含provider等信息
            
        Returns:
            str: 模型分析结果
        """
        # 构建用户任务提示词
        user_task = self.build_prompt(issue_desc, fix_code)
        
        # 构建请求消息
        model_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": user_task},
        ]
        

        # Call the model
        default_kwargs = {
            "model": settings.Claude_4_0_SONNET,
            "messages": model_messages,
            "stream": False,
            "temperature": 0.2,  # Lower temperature for accuracy and consistency
        }

        # Use get_client_with_kwargs to support context parameter overrides
        client, complete_kwargs = get_client_with_kwargs(context, default_kwargs)
        response = await client.chat_complete(**complete_kwargs)
        
        # 提取分析结果
        if response and response.choices and response.choices[0].message:
            analysis = response.choices[0].message.content
            if analysis:
                return analysis.strip()
        
        # 如果无法获取有效分析结果，返回错误信息
        raise Exception("无法从模型获取有效的分析结果")
    
    def build_prompt(self, issue_desc: str, fix_code: str) -> str:
        return f"""**Please systematically analyze whether the code modification truly resolves the issue by following the steps below and return your analysis in JSON format:**

---
Please systematically analyze whether the code modifications truly fix the problem by following these steps:

## Step 1: Deep Root Cause Analysis
1. **Core Problem Identification**: Extract the fundamental cause of the problem from the issue description, distinguishing between symptoms and true root causes
2. **Problem Impact Scope**: List all affected code paths, usage scenarios, and boundary conditions
3. **Problem Trigger Conditions**: Clarify under what conditions this problem will be triggered, with special attention to edge cases
4. **Expected Behavior Definition**: Based on the problem description, clearly define the specific behavior that should be achieved after the fix
5. **Reverse Logic Check**: Confirm whether the fix direction is correct, avoiding going in the opposite direction of expectations

## Step 2: Fix Strategy Rationality Assessment
1. **Fix Type Classification**:
   - Fundamental fix: Directly addresses the root cause
   - Symptomatic fix: Only masks or bypasses the error phenomenon
   - Compensatory fix: Avoids the problem through other mechanisms
2. **Solution Alignment**: Whether the fix solution directly targets the root cause
3. **Complexity Rationality**: Assess whether there is over-complication or over-engineering
4. **Minimal Intrusion Principle**: Whether it follows the principle of minimal changes, avoiding unnecessary modifications

## Step 3: Fix Code Implementation Quality Analysis
### 3.1 Coverage Assessment
1. **Modification Point Mapping**: Map each code modification point to specific problem scenarios
2. **Coverage Range Check**: Verify whether modifications cover all problem scenarios
3. **Missing Scenario Identification**: Identify uncovered scenarios that may have the same problem

### 3.2 Implementation Detail Analysis
1. **API Usage Appropriateness**: Verify whether the APIs used are the most direct and standard methods
2. **Code Execution Path**: Analyze whether there are unnecessary intermediate steps or roundabout implementations
3. **Error Handling Completeness**: Check whether all possible exception situations are correctly handled
4. **Performance Impact Assessment**: Analyze whether the fix introduces unnecessary performance overhead

## Step 4: Data Security and System Stability Check
1. **Data Security Risk**: Whether modifications may lead to data loss or inconsistency
2. **State Consistency**: Whether system state remains consistent after modifications
3. **Side Effect Assessment**: Evaluate whether modifications may introduce new problems
4. **Backward Compatibility**: Whether modifications maintain backward compatibility
5. **Rollback Safety**: Whether modifications support safe rollback

## Step 5: Design Principles and Architecture Consistency
1. **Architecture Alignment**: Whether modifications align with existing architecture and design patterns
2. **Framework Best Practices**: Whether they conform to the design philosophy and best practices of relevant frameworks
3. **Code Simplicity**: Whether the solution is concise, clear, easy to understand and maintain
4. **Maintainability Assessment**: Analyze the long-term maintainability and extensibility of the fix code

## Step 6: Test Verification Completeness
1. **Test Scenario Coverage**: Whether test cases cover all problem scenarios and boundary conditions
2. **Failed Case Analysis**: If there are test failures, analyze whether they indicate incomplete fixes
3. **Regression Test Verification**: Whether it's verified that modifications don't break existing functionality
4. **Performance Test Consideration**: Assess whether performance-related tests are needed to verify fix quality

## Step 7: Comprehensive Judgment and Recommendations
Based on the above analysis, provide clear conclusions:

### Required Output Fields:
1. **is_fixed**: true/false (partial fixes count as false)
2. **check_summary**: Detailed analysis summary, must include:
   - Specific basis for fix status judgment
   - If not fixed, clearly explain reasons for non-fix
   - If fixed, assess implementation quality and potential risks
   - Specific improvement suggestions or alternative solutions

## Key Analysis Focus:
- Whether the fundamental problem is truly solved rather than just making errors disappear
- Whether the fix direction is correct, avoiding directional errors
- Whether there's a tendency toward over-engineering
- Whether API usage is appropriate, avoiding roundabout or inefficient implementations
- Whether data security and system stability are ensured
- Long-term maintainability and extensibility of the code
---

## **Required JSON Output Format**

You must return your analysis in the following JSON format：

```json
{{
  "analysis": "The analysis results of each step",
  "result": {{
    "is_fixed": True,
    "check_summary": "Summary of each step of the analysis"
  }}
}}
```
---

**Problem Description:**
{issue_desc}

**Code Change:**
{fix_code}
"""
    
    def _parse_analysis_result(self, analysis_result: str) -> Dict[str, Any]:
        """解析模型分析结果
        
        Args:
            analysis_result: 模型返回的分析结果（应为JSON格式）
            
        Returns:
            Dict[str, Any]: 解析后的结果
        """
        try:
            # 尝试直接解析JSON，处理可能的markdown包装
            json_content = analysis_result.strip()
            
            # 如果响应被包装在markdown代码块中，提取JSON部分
            if json_content.startswith('```json') or json_content.startswith('```'):
                lines = json_content.split('\n')
                json_lines = []
                in_json_block = False
                for line in lines:
                    line_stripped = line.strip()
                    if line_stripped in ['```json', '```']:
                        if not in_json_block:
                            in_json_block = True
                        else:
                            break
                        continue
                    elif in_json_block:
                        json_lines.append(line)
                json_content = '\n'.join(json_lines)
            
            parsed_json = json.loads(json_content)
            
            # 验证JSON结构
            if not isinstance(parsed_json, dict):
                raise ValueError("返回的不是有效的JSON对象")
            
            # 提取结果信息
            result = parsed_json.get("result", {})
            analysis = parsed_json.get("analysis", "")
            
            # 如果analysis是字典类型，构建完整的分析文本
            if isinstance(analysis, dict):
                analysis_text = self._build_analysis_text(analysis)
            else:
                analysis_text = str(analysis)
            
            return {
                "is_fixed": result.get("is_fixed", False),
                "check_summary": result.get("check_summary", "未提供原因说明"),
                "analysis": analysis_text
            }
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # JSON解析失败，回退到文本解析
            return self._fallback_text_parsing(analysis_result, str(e))
    
    def _build_analysis_text(self, analysis: Dict[str, Any]) -> str:
        """从JSON分析数据构建完整的分析文本
        
        Args:
            analysis: 分析数据字典
            
        Returns:
            str: 格式化的分析文本
        """
        # 如果analysis是字符串，直接返回
        if isinstance(analysis, str):
            return analysis
            
        # 如果analysis是字典，尝试构建结构化文本
        if isinstance(analysis, dict):
            # 预定义的步骤名称映射
            step_mappings = [
                ("step1_problem_scope", "Step 1: Deep Root Cause Analysis"),
                ("step2_fix_coverage", "Step 2: Fix Strategy Rationality Assessment"),
                ("step3_test_validation", "Step 3: Fix Code Implementation Quality Analysis"),
                ("step4_logical_consistency", "Step 4: Data Security and System Stability Check"),
                ("step5_final_assessment", "Step 5: Design Principles and Architecture Consistency"),
                ("step6_test_verification", "Step 6: Test Verification Completeness"),
                ("step7_comprehensive_judgment", "Step 7: Comprehensive Judgment and Recommendations")
            ]
            
            formatted_sections = []
            
            # 处理结构化步骤
            for key, title in step_mappings:
                content = analysis.get(key, "")
                if content:
                    formatted_sections.append(f"## {title}\n{content}")
            
            # 如果没有找到标准步骤，处理其他键值对
            if not formatted_sections:
                for key, value in analysis.items():
                    if value:  # 只处理非空值
                        # 格式化键名为更可读的标题
                        title = key.replace("_", " ").title()
                        formatted_sections.append(f"## {title}\n{str(value)}")
            
            return "\n\n".join(formatted_sections) if formatted_sections else str(analysis)
        
        # 其他类型转换为字符串
        return str(analysis)
    
    def _fallback_text_parsing(self, analysis_result: str, error_msg: str) -> Dict[str, Any]:
        """当JSON解析失败时的回退文本解析方法
        
        Args:
            analysis_result: 原始分析结果
            error_msg: 错误信息
            
        Returns:
            Dict[str, Any]: 解析后的结果
        """
        # 使用原有的文本解析方法作为回退
        is_fixed = self._extract_fix_status(analysis_result)
        check_summary = self._extract_check_summary(analysis_result, is_fixed)
        
        # 在分析文本中添加解析错误信息
        analysis_with_error = f"[JSON解析失败: {error_msg}]\n\n{analysis_result}"
        
        return {
            "is_fixed": is_fixed,
            "check_summary": check_summary,
            "analysis": analysis_with_error
        }
    
    def _extract_fix_status(self, analysis: str) -> bool:
        """从分析结果中提取修复状态
        
        Args:
            analysis: 分析结果文本
            
        Returns:
            bool: 是否已修复
        """
        analysis_lower = analysis.lower()
        
        # 查找明确的修复状态指示
        if "fully fixed" in analysis_lower:
            return True
        elif "partially fixed" in analysis_lower or "not fixed" in analysis_lower:
            return False
        
        # 查找是否修复的明确回答
        if "is the issue fixed: yes" in analysis_lower:
            return True
        elif "is the issue fixed: no" in analysis_lower:
            return False
        
        # 如果没有明确指示，查找其他关键词
        positive_indicators = ["resolved", "addressed", "fixed", "solved"]
        negative_indicators = ["not resolved", "not addressed", "not fixed", "incomplete", "missing"]
        
        positive_count = sum(1 for indicator in positive_indicators if indicator in analysis_lower)
        negative_count = sum(1 for indicator in negative_indicators if indicator in analysis_lower)
        
        # 如果负面指示更多，认为未修复
        if negative_count > positive_count:
            return False
        
        # 默认情况下，如果有正面指示且没有明确的负面结论，认为已修复
        return positive_count > 0
    
    def _extract_check_summary(self, analysis: str, is_fixed: bool) -> str:
        """提取未修复的原因
        
        Args:
            analysis: 分析结果文本
            is_fixed: 是否已修复
            
        Returns:
            str: 原因说明
        """
        if is_fixed:
            return "问题已完全修复"
        
        # 尝试提取原因
        lines = analysis.split('\n')
        check_summary_lines = []
        
        # 查找包含原因的行
        for line in lines:
            line_lower = line.lower().strip()
            if any(keyword in line_lower for keyword in [
                "check_summary", "because", "however", "but", "missing",
                "not covered", "incomplete", "still exists"
            ]):
                check_summary_lines.append(line.strip())
        
        if check_summary_lines:
            return " ".join(check_summary_lines)
        
        return "分析表明问题未完全修复，但未明确说明具体原因"
