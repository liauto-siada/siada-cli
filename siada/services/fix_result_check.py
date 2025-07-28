"""
Fix Result Checker - 通过模型判断代码修复是否真正解决了问题
"""
from __future__ import annotations

import json
from typing import Dict, Any

from openai.types.chat import ChatCompletionMessageParam

from siada.provider.li.llm_connection import SiadaClient
from siada.foundation.config import settings


class FixResultChecker:
    """修复结果检查器
    
    使用模型分析代码修复是否真正解决了描述的问题
    """
    
    def __init__(self):
        """初始化检查器"""
        self.client = SiadaClient()
    
    async def check(self, issue_desc: str, fix_code: str) -> Dict[str, Any]:
        """检查修复代码是否真正解决了问题
        
        Args:
            issue_desc: 问题描述
            fix_code: 修复代码
            
        Returns:
            Dict[str, Any]: 包含检查结果的字典
            {
                "is_fixed": bool,      # 是否修复（部分修复算作未修复）
                "reason": str,         # 如果未修复，说明原因
                "analysis": str        # 完整的分析过程
            }
        """
        try:
            analysis_result = await self._call_model_for_analysis(issue_desc, fix_code)
            return self._parse_analysis_result(analysis_result)
        except Exception as e:
            return {
                "is_fixed": False,
                "reason": f"分析过程中发生错误: {str(e)}",
                "analysis": f"错误详情: {str(e)}"
            }
    
    async def _call_model_for_analysis(self, issue_desc: str, fix_code: str) -> str:
        """调用模型进行分析
        
        Args:
            issue_desc: 问题描述
            fix_code: 修复代码
            
        Returns:
            str: 模型分析结果
        """
        # 构建用户任务提示词
        user_task = self.build_prompt(issue_desc, fix_code)

        
        # 构建请求消息
        model_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": user_task},
        ]
        
        # 调用模型
        complete_kwargs = {
            "model": settings.Claude_4_0_SONNET,
            "messages": model_messages,
            "stream": False,
            "temperature": 0.2,  # 较低温度确保分析的准确性和一致性
        }
        
        response = await self.client.chat_complete(**complete_kwargs)
        
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

## **Analysis Steps**

### **Step 1: Problem Scope Analysis**
1. **Identify the core nature of the issue**: Extract the root cause and impact from the issue description.
2. **List all affected scenarios**: Identify all code paths and usage cases that could trigger the issue.
3. **Define the problem boundaries**: Clearly determine what operations, conditions, or states cause the issue to occur.

### **Step 2: Fix Coverage Evaluation**
1. **Map code changes to problem cases**: Match each code change to specific problem scenarios.
2. **Check coverage scope**: Verify whether the changes address all the scenarios identified in Step 1.
3. **Identify missing scenarios**: Highlight any possible scenarios where the issue may still exist but are not covered by the fix.

### **Step 3: Test Case Completeness Validation**
1. **Compare test scenarios**: Match the test cases against the actual impact range of the issue.
2. **Analyze failed cases**: If any tests fail, analyze whether the failure indicates an incomplete fix.
3. **Check boundary cases**: Confirm whether edge cases and exception scenarios are covered in testing.

### **Step 4: Logical Consistency Check**
1. **Validate fix logic**: Ensure that the fix correctly addresses the root cause of the issue.
2. **Assess side effects**: Evaluate whether the code changes may introduce new problems.
3. **Check design pattern alignment**: Verify whether the fix aligns with the overall design patterns and architectural conventions of the codebase.

### **Step 5: Final Assessment**
Based on the above analysis, provide a clear conclusion:
* **Fully Fixed**: The issue has been thoroughly resolved and all scenarios are covered.
* **Partially Fixed**: The main problem is addressed, but some scenarios remain uncovered. Clearly describe the uncovered parts.
* **Not Fixed**: The changes did not resolve the issue. Provide specific reasons.

---

## **Required JSON Output Format**

You must return your analysis in the following JSON format:

```json
{{
  "analysis": {{
    "step1_problem_scope": "Detailed analysis of problem scope including core nature, affected scenarios, and problem boundaries",
    "step2_fix_coverage": "Detailed evaluation of fix coverage including mapping to problem cases, coverage scope, and missing scenarios",
    "step3_test_validation": "Detailed test case completeness validation including scenario comparison, failed case analysis, and boundary cases",
    "step4_logical_consistency": "Detailed logical consistency check including fix logic validation, side effects assessment, and design pattern alignment",
    "step5_final_assessment": "Final assessment with clear conclusion on fix status"
  }},
  "result": {{
    "is_fixed": true/false,
    "reason": "Specific reason if not fixed, or confirmation if fixed"
  }}
}}
```

**Important**: 
- Return ONLY the JSON object, no additional text before or after
- Ensure the JSON is valid and properly formatted
- The "is_fixed" field should be false for partial fixes
- Provide detailed analysis in each step field

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
            if json_content.startswith('```json'):
                lines = json_content.split('\n')
                json_lines = []
                in_json_block = False
                for line in lines:
                    if line.strip() == '```json':
                        in_json_block = True
                        continue
                    elif line.strip() == '```' and in_json_block:
                        break
                    elif in_json_block:
                        json_lines.append(line)
                json_content = '\n'.join(json_lines)
            
            parsed_json = json.loads(json_content)
            
            # 验证JSON结构
            if not isinstance(parsed_json, dict):
                raise ValueError("返回的不是有效的JSON对象")
            
            # 提取结果信息
            result = parsed_json.get("result", {})
            analysis = parsed_json.get("analysis", {})
            
            # 构建完整的分析文本
            analysis_text = self._build_analysis_text(analysis)
            
            return {
                "is_fixed": result.get("is_fixed", False),
                "reason": result.get("reason", "未提供原因说明"),
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
        sections = [
            ("Step 1: Problem Scope Analysis", analysis.get("step1_problem_scope", "")),
            ("Step 2: Fix Coverage Evaluation", analysis.get("step2_fix_coverage", "")),
            ("Step 3: Test Case Completeness Validation", analysis.get("step3_test_validation", "")),
            ("Step 4: Logical Consistency Check", analysis.get("step4_logical_consistency", "")),
            ("Step 5: Final Assessment", analysis.get("step5_final_assessment", ""))
        ]
        
        formatted_sections = []
        for title, content in sections:
            if content:
                formatted_sections.append(f"## {title}\n{content}")
        
        return "\n\n".join(formatted_sections)
    
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
        reason = self._extract_reason(analysis_result, is_fixed)
        
        # 在分析文本中添加解析错误信息
        analysis_with_error = f"[JSON解析失败: {error_msg}]\n\n{analysis_result}"
        
        return {
            "is_fixed": is_fixed,
            "reason": reason,
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
    
    def _extract_reason(self, analysis: str, is_fixed: bool) -> str:
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
        reason_lines = []
        
        # 查找包含原因的行
        for line in lines:
            line_lower = line.lower().strip()
            if any(keyword in line_lower for keyword in [
                "reason", "because", "however", "but", "missing", 
                "not covered", "incomplete", "still exists"
            ]):
                reason_lines.append(line.strip())
        
        if reason_lines:
            return " ".join(reason_lines)
        
        return "分析表明问题未完全修复，但未明确说明具体原因"
