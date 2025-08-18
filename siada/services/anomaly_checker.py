"""
Anomaly Checker for Fix Result Analysis
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
                "anomaly_score": float,       # (0-10, higher means more anomalous)
                "patch_compliance": {         
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
                                  "description": f"error: {str(e)}"}],
                    "compliances": []
                },
                "summary_quality": {
                    "overall_score": 0.0,
                    "issues": [{"type": "analysis_error", "description": f"fail: {str(e)}"}],
                    "strengths": []
                },
                "recommendations": [f"**CRITICAL**: error: {str(e)}"],
                "detailed_analysis": f"error: {str(e)}"
            }

    async def _call_model_for_anomaly_analysis(
        self, 
        fix_result_check_summary: str,
        patch_diff: str,
        task_description: str,
        context: Any
    ) -> str:
                
        user_task = self._build_anomaly_check_prompt(
            fix_result_check_summary, patch_diff, task_description
        )
        
        model_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": user_task},
        ]
        
        print("Running anomaly check analysis...")

        default_kwargs = {
            "model": settings.Claude_4_0_SONNET,
            "messages": model_messages,
            "stream": False,
            "temperature": 0.1,  
        }

        client, complete_kwargs = get_client_with_kwargs(context, default_kwargs)
        response = await client.chat_complete(**complete_kwargs)
        
        if response and response.choices and response.choices[0].message:
            analysis = response.choices[0].message.content
            if analysis:
                return analysis.strip()
        
        raise Exception("Failed to get valid response from model")

    def _build_anomaly_check_prompt(
        self, 
        fix_result_check_summary: str,
        patch_diff: str,
        task_description: str
    ) -> str:
        
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
        try:
            json_content = analysis_result.strip()
            
            if '```json' in json_content:
                json_start = json_content.find('```json') + len('```json')
                json_end = json_content.rfind('```')
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_content = json_content[json_start:json_end]
            
            parsed_json = json.loads(json_content)
            
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
                        "description": "",
                        "evidence": ""
                    },
                    "completeness_assessment": {
                        "score": 0.0,
                        "description": "",
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
                "detailed_analysis": anomaly_analysis.get("detailed_analysis", "No detailed analysis provided")
            }
            
            if result["anomaly_score"] > 10.0:
                result["anomaly_score"] = 10.0
            elif result["anomaly_score"] < 0.0:
                result["anomaly_score"] = 0.0
                
            if result["anomaly_score"] >= 5.0:
                result["is_anomaly"] = True
            
            return result
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Failed to parse anomaly analysis result: {e}")
            return self._fallback_anomaly_parsing(analysis_result, str(e))
    
    def _fallback_anomaly_parsing(self, analysis_result: str, error_msg: str) -> Dict[str, Any]:
        
        analysis_lower = analysis_result.lower()
        
        anomaly_indicators = [
            "violation", "error", "problem", "issue", "missing", "failure", 
            "incorrect", "invalid", "generic", "lack of specificity"
        ]
        
        anomaly_count = sum(1 for indicator in anomaly_indicators 
                          if indicator in analysis_lower)
        
        # Calculate anomaly score based on indicator count
        anomaly_score = min(10.0, anomaly_count * 1.5)
        is_anomaly = anomaly_score >= 5.0
        
        return {
            "is_anomaly": is_anomaly,
            "anomaly_score": anomaly_score,
            "patch_compliance": {
                "overall_score": max(0.0, 10.0 - anomaly_score),
                "violations": [
                    {
                        "rule": "parsing_error",
                        "severity": "Critical",
                        "description": f"Failed to parse analysis result: {error_msg}",
                        "evidence": "JSON parsing failed",
                        "suggestion": "Check model output format"
                    }
                ],
                "compliances": []
            },
            "summary_quality": {
                "overall_score": max(0.0, 10.0 - anomaly_score),
                "issues": [
                    {
                        "type": "parsing_error",
                        "description": f"Analysis result format error: {error_msg}",
                        "suggestion": "Ensure output conforms to JSON format requirements"
                    }
                ],
                "strengths": []
            },
            "recommendations": [
                f"**CRITICAL**: Fix analysis result parsing error: {error_msg}",
                "**IMPORTANT**: Ensure model output conforms to expected JSON format"
            ],
            "detailed_analysis": f"Failed to parse original analysis result:\n{analysis_result}\n\nError message: {error_msg}"
        }

    def get_anomaly_summary(self, anomaly_result: Dict[str, Any]) -> str:
        """Generate anomaly check summary"""
        
        is_anomaly = anomaly_result.get("is_anomaly", False)
        anomaly_score = anomaly_result.get("anomaly_score", 0.0)
        
        if not is_anomaly:
            return f"✅ No anomaly detected (Score: {anomaly_score:.1f}/10.0) - Fix result meets quality standards"
        
        patch_compliance = anomaly_result.get("patch_compliance", {})
        summary_quality = anomaly_result.get("summary_quality", {})
        
        violations_count = len(patch_compliance.get("violations", []))
        issues_count = len(summary_quality.get("issues", []))
        
        severity_levels = []
        if anomaly_score >= 8.0:
            severity_levels.append("🔴 Critical Anomaly")
        elif anomaly_score >= 6.0:
            severity_levels.append("🟠 Moderate Anomaly")
        else:
            severity_levels.append("🟡 Minor Anomaly")
            
        summary = f"{' '.join(severity_levels)} (Score: {anomaly_score:.1f}/10.0)"
        
        if violations_count > 0:
            summary += f" - Found {violations_count} rule violations"
        if issues_count > 0:
            summary += f" - Found {issues_count} quality issues"
            
        return summary
