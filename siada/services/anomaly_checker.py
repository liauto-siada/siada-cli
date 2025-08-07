"""
Anomaly Checker for Fix Result Analysis
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, List, Optional

from openai.types.chat import ChatCompletionMessageParam

from siada.provider.client_factory import get_client_with_kwargs
from siada.foundation.setting import settings

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
        
        # Rule library mapping
        self.rule_library = {
            "task_solution_adherence": "You need to find solutions and suggestions from the task tags, and you must implement and follow them unconditionally.",
            "existing_feature_reuse": "When solving problems, prioritize using the project's existing features and tools rather than redeveloping them from scratch.",
            "data_calculation_strategy": "When you need to get some data or a variable, consider calculating it from the current class's existing data or variables instead of starting from scratch.",
            "exception_safety": "You need ensure that the modified code does not throw new exceptions.",
            "test_coverage_completeness": """you can try to use the test in original codebase to reproduce the bug.
You need to **create and pass test cases** that cover the following scenarios:
--Normal Functionality: Testing the core, expected behavior of the class methods.
--Edge Cases: Checking the behavior of methods with boundary values, such as empty lists, zero values, or maximum limits.
--State and Attribute Changes: Ensuring that the internal state and attributes of an object are updated correctly after a method is called.
--Uninitialized Attributes: Testing how the class behaves when an attribute is accessed before it has been explicitly assigned a value.
--Data Types and Format: Validating that the class methods accept and process the correct data types and reject incorrect ones.""",
            "root_cause_analysis_depth": """Deep Root Cause Analysis: Don't just patch symptoms. You must trace the bug's origin, whether it stems from a flawed assumption, an incomplete logical condition, or an unhandled edge case. Your job is to understand why the problem occurs, not just where.
Surgical Precision: Apply fixes with the highest level of accuracy. Your changes should be minimal and localized. This often means:
--Adding a more precise conditional check.
--Constraining a loop or iteration's boundary.
--Preventing an incorrect type conversion or improper simplification.
--Using the most suitable underlying primitive or data structure for the task."""
        }

    async def check_anomaly(
        self, 
        fix_result_check_summary: str,
        patch_diff: str,
        task_description: str = "",
        context: Any = None
    ) -> Dict[str, Any]:
        """
        Evaluate patch against six compliance rules and return the best matching rule guidance
        
        Returns:
            Dict[str, Any]: 
            {
                "rule_scores": Dict[str, Dict],  # Scores for all 6 rules
                "best_matching_rule": {          # Highest scoring rule with guidance
                    "rule_name": str,
                    "total_score": float,
                    "reasoning": str,
                    "guidance": str
                },
                "summary": Dict[str, Any],       # Evaluation summary
                "evaluation_success": bool      # Whether evaluation succeeded
            }
        """
        try:
            # Execute six-rule compliance evaluation
            rule_evaluation_result = await self.evaluate_patch_compliance_rules(
                patch_diff, task_description, fix_result_check_summary, context
            )
            return rule_evaluation_result
        except Exception as e:
            logger.error(f"Rule evaluation failed: {e}", exc_info=True)
            # Return fallback with default rule
            return {
                "rule_scores": {rule: {"total_score": 0.0} for rule in self.compliance_rules},
                "best_matching_rule": {
                    "rule_name": "task_solution_adherence",
                    "total_score": 0.0,
                    "reasoning": f"Rule evaluation failed: {str(e)}",
                    "guidance": self.rule_library["task_solution_adherence"]
                },
                "summary": {"error": f"Evaluation failed: {str(e)}"},
                "evaluation_success": False
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
        response = await client.completion(**complete_kwargs)
        
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

    async def evaluate_patch_compliance_rules(
        self, 
        patch_diff: str, 
        task_description: str, 
        fix_result_check_summary: str,
        context: Any = None
    ) -> Dict[str, Any]:
        """
        Use LLM to evaluate patch against six compliance rules and return the best matching rule
        
        Returns:
            Dict containing rule scores and the highest scoring rule with its guidance
        """
        
        rule_evaluation_result = await self._call_model_for_rule_evaluation(
            patch_diff, task_description, fix_result_check_summary, context
        )
        
        return self._parse_rule_evaluation_result(rule_evaluation_result)

    async def _call_model_for_rule_evaluation(
        self, 
        patch_diff: str,
        task_description: str,
        fix_result_check_summary: str,
        context: Any
    ) -> str:
        """Call LLM to evaluate patch against compliance rules"""
        
        user_task = self._build_rule_evaluation_prompt(
            patch_diff, task_description, fix_result_check_summary
        )
        
        model_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": user_task},
        ]
        
        print("Running patch compliance rule evaluation...")

        default_kwargs = {
            "model": settings.Claude_4_0_SONNET,
            "messages": model_messages,
            "stream": False,
            "temperature": 0.1,  
        }

        client, complete_kwargs = get_client_with_kwargs(context, default_kwargs)
        response = await client.completion(**complete_kwargs)
        
        if response and response.choices and response.choices[0].message:
            analysis = response.choices[0].message.content
            if analysis:
                return analysis.strip()
        
        raise Exception("Failed to get valid response from model for rule evaluation")

    def _build_rule_evaluation_prompt(
        self, 
        patch_diff: str,
        task_description: str,
        fix_result_check_summary: str
    ) -> str:
        """Build prompt for rule evaluation"""
        
        return f"""
You are a **Code Review Agent (Agent 3)**, responsible for working in the **third stage** of the issue resolution workflow. The current process has four steps:

1. **Initial Resolution**: Agent 1 attempts to resolve the issue based on the problem description, generating a solution trace and code patch.
2. **Review & Verification**: Agent 2 verifies whether the issue is fully resolved; if not, it produces a review conclusion.
3. **Rule Filtering (your stage)**: Based on the incremental information from the first two steps, you identify the key rules from the given rule list that were not followed.
4. **Iterative Improvement**: Agent 1 improves the solution based on the rules you provide.

---

### **Your Specific Responsibilities**

**Strict Evidence Requirements**: A rule can only be selected if **all** the following conditions are met:
✅ The rule is directly relevant to the current issue
✅ Clear evidence of violation can be found in the problem description, solution process, or code patch
✅ The violation of this rule directly impacts the effectiveness of the issue resolution

---

### **Prohibited Actions**

❌ Guessing rules when no clear evidence exists
❌ Selecting generic rules that are unrelated to the current issue
❌ Choosing rules merely because they "might be useful"


## **🔍 Six Compliance Rules to Evaluate**

### **1. Task Solution Adherence**
**Rule**: {self.rule_library["task_solution_adherence"]}

### **2. Existing Feature Reuse**
**Rule**: {self.rule_library["existing_feature_reuse"]}

### **3. Data Calculation Strategy**
**Rule**: {self.rule_library["data_calculation_strategy"]}

### **4. Exception Safety**
**Rule**: {self.rule_library["exception_safety"]}

### **5. Test Coverage Completeness**
**Rule**: {self.rule_library["test_coverage_completeness"]}

### **6. Root Cause Analysis Depth**
**Rule**: {self.rule_library["root_cause_analysis_depth"]}

---

## **📊 Input Data**

### **📝 Task Description**
```
{task_description}
```

### **🔧 Patch Diff**
```
{patch_diff}
```

### **📋 Fix Result Check Summary**
```
{fix_result_check_summary}
```

---

## **🎯 Evaluation Requirements**

For each of the 6 rules, provide:
1. **Relevance Score (0-10)**: How relevant is this rule to the current patch?
2. **Compliance Score (0-10)**: How well does the patch comply with this rule?
3. **Evidence**: Specific evidence from the patch/task/summary
4. **Improvement Potential**: How much could following this rule improve the patch?

**Scoring Guidelines:**
- **Relevance Score**: 
  - 10 = Extremely relevant to this type of patch/task
  - 5 = Moderately relevant
  - 0 = Not relevant at all
- **Compliance Score**:
  - 10 = Perfect compliance with the rule
  - 5 = Partial compliance
  - 0 = No compliance or violation of the rule

---

## **📋 Required Output Format**

```json
{{
  "rule_evaluation": {{
    "task_solution_adherence": {{
      "relevance_score": 8.5,
      "compliance_score": 6.0,
      "evidence": "Patch modifies exec() call but doesn't follow task requirement for empty dictionary",
      "improvement_potential": 9.0,
      "total_score": 23.5
    }},
    "existing_feature_reuse": {{
      "relevance_score": 3.0,
      "compliance_score": 7.0,
      "evidence": "Patch uses existing exec() function appropriately",
      "improvement_potential": 2.0,
      "total_score": 12.0
    }},
    "data_calculation_strategy": {{
      "relevance_score": 2.0,
      "compliance_score": 8.0,
      "evidence": "No complex data calculations involved in this patch",
      "improvement_potential": 1.0,
      "total_score": 11.0
    }},
    "exception_safety": {{
      "relevance_score": 7.0,
      "compliance_score": 5.0,
      "evidence": "Patch doesn't add exception handling for exec() calls",
      "improvement_potential": 6.0,
      "total_score": 18.0
    }},
    "test_coverage_completeness": {{
      "relevance_score": 6.0,
      "compliance_score": 3.0,
      "evidence": "No test cases provided with the patch",
      "improvement_potential": 8.0,
      "total_score": 17.0
    }},
    "root_cause_analysis_depth": {{
      "relevance_score": 9.0,
      "compliance_score": 4.0,
      "evidence": "Patch addresses symptom but may not solve root cause of namespace issue",
      "improvement_potential": 9.0,
      "total_score": 22.0
    }},
    "best_matching_rule": {{
      "rule_name": "task_solution_adherence",
      "total_score": 23.5,
      "reasoning": "This rule has the highest total score and is most relevant for improving the patch to better follow task requirements"
    }},
    "summary": {{
      "highest_relevance_rule": "root_cause_analysis_depth",
      "lowest_compliance_rule": "test_coverage_completeness", 
      "most_improvement_potential": "task_solution_adherence",
      "overall_assessment": "Patch needs better task adherence and deeper root cause analysis"
    }}
  }}
}}
```

---

## **⚠️ Evaluation Principles**

1. **Evidence-Based**: Every score must be supported by specific evidence
2. **Context-Aware**: Consider the specific task and patch context
3. **Improvement-Focused**: Identify which rule would most improve the patch
4. **Balanced Assessment**: Don't just focus on violations, also recognize good practices
5. **Actionable Insights**: Provide clear guidance for the next model iteration

**Focus on identifying the rule that would provide the most valuable guidance for improving this specific patch!**
"""

    def _parse_rule_evaluation_result(self, evaluation_result: str) -> Dict[str, Any]:
        """Parse the rule evaluation result from LLM"""
        try:
            json_content = evaluation_result.strip()
            
            if '```json' in json_content:
                json_start = json_content.find('```json') + len('```json')
                json_end = json_content.rfind('```')
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_content = json_content[json_start:json_end]
            
            parsed_json = json.loads(json_content)
            rule_evaluation = parsed_json.get("rule_evaluation", {})
            
            # Extract rule scores
            rule_scores = {}
            for rule_name in self.compliance_rules:
                rule_data = rule_evaluation.get(rule_name, {})
                rule_scores[rule_name] = {
                    "relevance_score": rule_data.get("relevance_score", 0.0),
                    "compliance_score": rule_data.get("compliance_score", 0.0),
                    "evidence": rule_data.get("evidence", ""),
                    "improvement_potential": rule_data.get("improvement_potential", 0.0),
                    "total_score": rule_data.get("total_score", 0.0)
                }
            
            # Get best matching rule
            best_rule_info = rule_evaluation.get("best_matching_rule", {})
            best_rule_name = best_rule_info.get("rule_name", "task_solution_adherence")
            
            return {
                "rule_scores": rule_scores,
                "best_matching_rule": {
                    "rule_name": best_rule_name,
                    "total_score": best_rule_info.get("total_score", 0.0),
                    "reasoning": best_rule_info.get("reasoning", ""),
                    "guidance": self.rule_library.get(best_rule_name, "")
                },
                "summary": rule_evaluation.get("summary", {}),
                "evaluation_success": True
            }
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Failed to parse rule evaluation result: {e}")
            
            # Fallback to default rule
            return {
                "rule_scores": {rule: {"total_score": 5.0} for rule in self.compliance_rules},
                "best_matching_rule": {
                    "rule_name": "task_solution_adherence",
                    "total_score": 5.0,
                    "reasoning": f"Evaluation parsing failed: {str(e)}",
                    "guidance": self.rule_library["task_solution_adherence"]
                },
                "summary": {"error": f"Parsing failed: {str(e)}"},
                "evaluation_success": False
            }
