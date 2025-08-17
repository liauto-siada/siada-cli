"""
Anomaly Checker for Fix Result Analysis
检查修复结果是否存在异常，包括patch_diff合规性和summary质量评估
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, List, Optional

from openai.types.chat import ChatCompletionMessageParam

from siada.provider.client_factory import get_client_with_kwargs
from siada.foundation.config import settings

logger = logging.getLogger(__name__)


class AnomalyChecker:
    
    def __init__(self):
        self.compliance_rules = [
            "task_solution_adherence",
            "existing_feature_reuse", 
            "data_calculation_strategy",
            "exception_safety",
            "test_coverage_completeness",
            "root_cause_analysis_depth"
        ]
        
        self.summary_quality_criteria = [
            "task_specificity",
            "project_context_understanding", 
            "technical_specificity",
            "solution_orientation"
        ]

    async def check_anomaly(
        self, 
        fix_result_check_summary: str,
        patch_diff: str,
        task_description: str = "",
        context: Any = None
    ) -> Dict[str, Any]:
        """
        check anmaly in the fix result and last check summary
        
        Returns:
            Dict[str, Any]: 
            {
                "is_anomaly": bool,           
                "anomaly_score": float,       # (0-10, 越高越异常)
                "patch_compliance": {         # patch合规性检查结果
                    "overall_score": float,
                    "violations": List[Dict],
                    "compliances": List[Dict]
                },
                "summary_quality": {        
                    "overall_score": float,
                    "issues": List[Dict],
                    "strengths": List[str]
                },
                "recommendations": List[str],
                "detailed_analysis": str     
            }
        """
        try:
            analysis_result = await self._call_model_for_anomaly_analysis(
                fix_result_check_summary, patch_diff, task_description, context
            )
            return self._parse_anomaly_analysis_result(analysis_result)
        except Exception as e:
            logger.error(f"Anomaly check failed: {e}", exc_info=True)
            return {
                "is_anomaly": True,
                "anomaly_score": 10.0,
                "patch_compliance": {
                    "overall_score": 0.0,
                    "violations": [{"rule": "analysis_error", "severity": "Critical", 
                                  "description": f"检查过程出错: {str(e)}"}],
                    "compliances": []
                },
                "summary_quality": {
                    "overall_score": 0.0,
                    "issues": [{"type": "analysis_error", "description": f"分析失败: {str(e)}"}],
                    "strengths": []
                },
                "recommendations": [f"**CRITICAL**: 修复异常检查错误: {str(e)}"],
                "detailed_analysis": f"异常检查过程中发生错误: {str(e)}"
            }

    async def _call_model_for_anomaly_analysis(
        self, 
        fix_result_check_summary: str,
        patch_diff: str,
        task_description: str,
        context: Any
    ) -> str:
        """调用模型进行异常分析"""
        
        user_task = self._build_anomaly_check_prompt(
            fix_result_check_summary, patch_diff, task_description
        )
        
        model_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": user_task},
        ]
        
        print("Running anomaly check analysis...")

        # 调用模型
        default_kwargs = {
            "model": settings.Claude_4_0_SONNET,
            "messages": model_messages,
            "stream": False,
            "temperature": 0.1,  # 更低的温度确保一致性
        }

        # 如果没有提供context，创建一个简单的context对象
        if context is None:
            # 创建一个简单的context对象，使用默认的provider
            class SimpleContext:
                def __init__(self):
                    self.provider = "li"  # 使用默认的li provider
            context = SimpleContext()

        # 使用 get_client_with_kwargs 支持上下文参数覆盖
        client, complete_kwargs = get_client_with_kwargs(context, default_kwargs)
        response = await client.chat_complete(**complete_kwargs)
        
        if response and response.choices and response.choices[0].message:
            analysis = response.choices[0].message.content
            if analysis:
                return analysis.strip()
        
        raise Exception("无法从模型响应中获取异常分析结果")

    def _build_anomaly_check_prompt(
        self, 
        fix_result_check_summary: str,
        patch_diff: str,
        task_description: str
    ) -> str:
        """构建异常检查的提示词"""
        
        return f"""
# 🔍 **SIADA Fix Result Anomaly Detection Expert**

You are a **Senior Code Review Expert** and **AI Agent Behavior Analyst** specializing in detecting anomalies in fix results.

## **🎯 Analysis Mission**

You need to perform **comprehensive anomaly detection** focusing on **patch-task consistency** and summary quality:

### **📋 Primary Analysis Focus**

#### **🎯 CRITICAL: Patch-Task Consistency Analysis**
**This is the MOST IMPORTANT aspect of your analysis.**

Evaluate how well the patch_diff aligns with the task description:

**📊 Consistency Scoring (0-10)**:
- **9-10**: Perfect alignment - patch directly addresses all task requirements
- **7-8**: Good alignment - patch addresses main requirements with minor gaps
- **5-6**: Moderate alignment - patch partially addresses requirements
- **3-4**: Poor alignment - patch addresses some requirements but misses key aspects
- **0-2**: No alignment - patch doesn't address task requirements or goes in wrong direction

**🔍 Consistency Check Points**:
1. **Requirement Coverage**: Does the patch address all stated requirements in the task?
2. **Implementation Direction**: Is the patch implementing the solution as described in the task?
3. **Scope Alignment**: Is the patch scope appropriate for the task complexity?
4. **Method Consistency**: Are the implementation methods consistent with task suggestions?
5. **Completeness**: Does the patch provide a complete solution for the task?

#### **📝 Summary Quality Assessment**
**Key Logic**: Summary quality should be evaluated based on how well it aligns with and reflects the actual task requirements and patch-task consistency.

**🎯 Summary-Task Alignment Evaluation**:
- **High Quality**: Summary accurately reflects task requirements and correctly identifies patch-task alignment/misalignment
- **Medium Quality**: Summary partially addresses task requirements but misses some key aspects
- **Low Quality**: Summary is generic, doesn't address task specifics, or incorrectly assesses patch-task relationship

**🚨 Summary Quality Issues**:
- Generic statements that could apply to any fix regardless of task specifics
- Incorrect assessment of patch-task alignment (e.g., saying patch is good when it violates task requirements)
- Missing analysis of how patch addresses (or fails to address) specific task requirements
- Overly positive assessment when patch has serious task compliance issues

---

## **📊 Input Data**

### **📝 Task Description (Requirements)**
```
{task_description}
```

### **🔧 Code Modification Diff (PATCH_DIFF)**
```
{patch_diff}
```

### **📋 Fix Result Check Summary**
```
{fix_result_check_summary}
```

---

## **🎯 Analysis Requirements**

### **🔍 Step 1: Patch-Task Consistency Analysis**
1. **Requirement Mapping**: Map each task requirement to specific patch changes
2. **Implementation Verification**: Verify if patch implements the requested solution correctly
3. **Completeness Assessment**: Check if all task aspects are addressed
4. **Consistency Scoring**: Provide detailed 0-10 consistency score with justification

### **📝 Step 2: Summary Quality Analysis**
**CRITICAL**: Summary quality should be evaluated based on how accurately it reflects the actual task requirements, NOT just patch quality.

**🎯 Key Evaluation Criteria**:
1. **Task Requirements Understanding**: Does the summary demonstrate correct understanding of what the task actually requires?
2. **Task-Specific Evaluation**: Does the summary evaluate the patch against the specific task requirements?
3. **Requirement Alignment**: If task says "use X", does summary correctly identify whether patch uses X or not?
4. **Appropriate Assessment**: Does summary's evaluation align with the actual task specifications?

**🎯 Summary Quality Scoring Logic**:
- **High Score (8-10)**: Summary correctly understands task requirements and accurately evaluates patch against them
- **Medium Score (5-7)**: Summary partially understands task requirements but has some misalignment
- **Low Score (0-4)**: Summary misunderstands task requirements or evaluates patch against wrong criteria

**🚨 MANDATORY LOW SCORE (0-4) CONDITIONS**:
- **Task Opposition**: Summary explicitly argues AGAINST task-specified solutions
- **Requirement Contradiction**: Summary supports approaches that DIRECTLY CONTRADICT task instructions
- **Wrong Evaluation Criteria**: Summary evaluates patch based on general principles INSTEAD OF specific task requirements
- **Task Ignorance**: Summary completely FAILS to reference or acknowledge the specific task requirements

**⚠️ CRITICAL EXAMPLE**: 
- Task says: "use empty dictionary as second argument of exec"
- Summary says: "using empty dictionary will cause problems"
- **RESULT**: AUTOMATIC LOW SCORE (0-4) regardless of technical analysis quality!

**🔥 ABSOLUTE RULE**: If summary opposes task requirements = LOW SCORE (0-4)!

**📋 SPECIFIC CASE TO CHECK**:
In this analysis, if the task explicitly mentions "passing a new, empty dictionary as the second argument of exec" and the summary argues against using empty dictionary (saying it will cause problems), then the summary quality MUST be scored 0-4, NOT 8-10!

### **🏆 Step 3: Anomaly Detection Logic**
- **Low Patch-Task Consistency + Summary Opposes Task Requirements = Major Anomaly** (Both patch and summary violate task)
- **Low Patch-Task Consistency + Summary Supports Task Requirements = Medium Anomaly** (Patch bad, summary good)
- **High Patch-Task Consistency + Summary Opposes Task Requirements = Medium Anomaly** (Patch good, summary bad)
- **High Patch-Task Consistency + Summary Supports Task Requirements = No Anomaly** (Both aligned with task)

---

## **📋 Required Output Format**

```json
{{
  "anomaly_analysis": {{
    "is_anomaly": false,
    "anomaly_score": 3.2,
    "patch_task_consistency": {{
      "consistency_score": 8.5,
      "requirement_coverage": {{
        "covered_requirements": ["Requirement 1", "Requirement 2"],
        "missed_requirements": ["Requirement 3"],
        "coverage_percentage": 85.0
      }},
      "implementation_alignment": {{
        "score": 8.0,
        "description": "Patch correctly implements the requested validation logic",
        "evidence": "Added validation_utils.validate_input() as specified in task"
      }},
      "completeness_assessment": {{
        "score": 9.0,
        "description": "Patch provides complete solution for all main requirements",
        "gaps": []
      }}
    }},
    "summary_quality": {{
      "overall_score": 6.8,
      "objectivity_level": "High",
      "task_specificity_score": 4.0,
      "issues": [
        {{
          "type": "Over-Objective",
          "description": "Summary uses generic descriptions despite high patch-task consistency",
          "evidence": "Uses phrases like 'generally good' instead of specific task-related analysis",
          "suggestion": "Should specifically mention how patch addresses task requirement X"
        }}
      ],
      "strengths": [
        "Identifies technical correctness",
        "Mentions code quality aspects"
      ]
    }},
    "patch_compliance": {{
      "overall_score": 7.5,
      "violations": [],
      "compliances": [
        {{
          "rule": "Task Solution Adherence",
          "evidence": "Patch directly implements task requirements",
          "description": "Code changes align with specified task objectives"
        }}
      ]
    }},
    "recommendations": [
      "**CRITICAL**: Summary should provide task-specific analysis given high patch-task consistency",
      "**IMPORTANT**: Include specific evidence of how patch addresses each task requirement",
      "**RECOMMENDED**: Connect implementation details to original task objectives"
    ],
    "detailed_analysis": "Detailed analysis focusing on patch-task consistency and summary quality assessment"
  }}
}}
```

---

## **⚠️ Critical Analysis Principles**

1. **🎯 Consistency First**: Patch-task consistency is the primary evaluation criterion
2. **📊 Evidence-Driven**: Every judgment must be supported by specific evidence
3. **🔍 Context-Aware**: Consider task complexity and implementation requirements
4. **💡 Quality-Focused**: High consistency should lead to high-quality, specific summaries
5. **🚨 Anomaly Detection**: Flag cases where good implementation gets generic analysis

**Focus on patch-task consistency and identify summary quality issues when consistency is high but analysis is generic!**
"""

    def _parse_anomaly_analysis_result(self, analysis_result: str) -> Dict[str, Any]:
        """解析异常分析结果"""
        try:
            json_content = analysis_result.strip()
            
            # 提取JSON内容
            if '```json' in json_content:
                json_start = json_content.find('```json') + len('```json')
                json_end = json_content.rfind('```')
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_content = json_content[json_start:json_end]
            
            parsed_json = json.loads(json_content)
            
            # 提取异常分析结果
            anomaly_analysis = parsed_json.get("anomaly_analysis", {})
            
            result = {
                "is_anomaly": anomaly_analysis.get("is_anomaly", False),
                "anomaly_score": anomaly_analysis.get("anomaly_score", 0.0),
                "patch_task_consistency": anomaly_analysis.get("patch_task_consistency", {
                    "consistency_score": 0.0,
                    "requirement_coverage": {
                        "covered_requirements": [],
                        "missed_requirements": [],
                        "coverage_percentage": 0.0
                    },
                    "implementation_alignment": {
                        "score": 0.0,
                        "description": "未提供对齐分析",
                        "evidence": "无证据"
                    },
                    "completeness_assessment": {
                        "score": 0.0,
                        "description": "未提供完整性评估",
                        "gaps": []
                    }
                }),
                "patch_compliance": anomaly_analysis.get("patch_compliance", {
                    "overall_score": 0.0,
                    "violations": [],
                    "compliances": []
                }),
                "summary_quality": anomaly_analysis.get("summary_quality", {
                    "overall_score": 0.0,
                    "objectivity_level": "Unknown",
                    "task_specificity_score": 0.0,
                    "issues": [],
                    "strengths": []
                }),
                "recommendations": anomaly_analysis.get("recommendations", []),
                "detailed_analysis": anomaly_analysis.get("detailed_analysis", "未提供详细分析")
            }
            
            # 确保异常评分在合理范围内
            if result["anomaly_score"] > 10.0:
                result["anomaly_score"] = 10.0
            elif result["anomaly_score"] < 0.0:
                result["anomaly_score"] = 0.0
                
            # 根据评分自动判断是否异常
            if result["anomaly_score"] >= 5.0:
                result["is_anomaly"] = True
            
            return result
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Failed to parse anomaly analysis result: {e}")
            return self._fallback_anomaly_parsing(analysis_result, str(e))
    
    def _fallback_anomaly_parsing(self, analysis_result: str, error_msg: str) -> Dict[str, Any]:
        """异常分析结果解析失败时的回退处理"""
        
        # 简单的文本分析来提取关键信息
        analysis_lower = analysis_result.lower()
        
        # 检测是否存在异常指标
        anomaly_indicators = [
            "violation", "违反", "问题", "异常", "错误", "缺失", 
            "不符合", "未遵循", "过于客观", "缺乏针对性"
        ]
        
        anomaly_count = sum(1 for indicator in anomaly_indicators 
                          if indicator in analysis_lower)
        
        # 基于指标数量估算异常评分
        anomaly_score = min(10.0, anomaly_count * 1.5)
        is_anomaly = anomaly_score >= 5.0
        
        return {
            "is_anomaly": is_anomaly,
            "anomaly_score": anomaly_score,
            "patch_compliance": {
                "overall_score": max(0.0, 10.0 - anomaly_score),
                "violations": [
                    {
                        "rule": "解析错误",
                        "severity": "Critical",
                        "description": f"无法解析分析结果: {error_msg}",
                        "evidence": "JSON解析失败",
                        "suggestion": "检查模型输出格式"
                    }
                ],
                "compliances": []
            },
            "summary_quality": {
                "overall_score": max(0.0, 10.0 - anomaly_score),
                "issues": [
                    {
                        "type": "解析错误",
                        "description": f"分析结果格式错误: {error_msg}",
                        "suggestion": "确保输出符合JSON格式要求"
                    }
                ],
                "strengths": []
            },
            "recommendations": [
                f"**CRITICAL**: 修复分析结果解析错误: {error_msg}",
                "**IMPORTANT**: 确保模型输出符合预期的JSON格式"
            ],
            "detailed_analysis": f"解析失败的原始分析结果:\n{analysis_result}\n\n错误信息: {error_msg}"
        }

    def get_anomaly_summary(self, anomaly_result: Dict[str, Any]) -> str:
        """生成异常检查摘要"""
        
        is_anomaly = anomaly_result.get("is_anomaly", False)
        anomaly_score = anomaly_result.get("anomaly_score", 0.0)
        
        if not is_anomaly:
            return f"✅ 未发现异常 (评分: {anomaly_score:.1f}/10.0) - 修复结果符合质量标准"
        
        patch_compliance = anomaly_result.get("patch_compliance", {})
        summary_quality = anomaly_result.get("summary_quality", {})
        
        violations_count = len(patch_compliance.get("violations", []))
        issues_count = len(summary_quality.get("issues", []))
        
        severity_levels = []
        if anomaly_score >= 8.0:
            severity_levels.append("🔴 严重异常")
        elif anomaly_score >= 6.0:
            severity_levels.append("🟠 中等异常")
        else:
            severity_levels.append("🟡 轻微异常")
            
        summary = f"{' '.join(severity_levels)} (评分: {anomaly_score:.1f}/10.0)"
        
        if violations_count > 0:
            summary += f" - 发现 {violations_count} 项规则违反"
        if issues_count > 0:
            summary += f" - 发现 {issues_count} 项质量问题"
            
        return summary
