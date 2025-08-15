"""
Enhanced Fix Result Checker with Execution Trace Analysis
"""
from __future__ import annotations

import json
from typing import Dict, Any, Optional

from openai.types.chat import ChatCompletionMessageParam

from siada.provider.client_factory import get_client_with_kwargs
from siada.foundation.config import settings
from siada.services.execution_trace_collector import ExecutionTrace


class EnhancedFixResultChecker:
    """Enhanced Fix Result Checker
    """
    
    async def check_with_trace(
        self, 
        issue_desc: str, 
        fix_code: str,
        context: Any,
        execution_trace: Optional[ExecutionTrace] = None
    ) -> Dict[str, Any]:
        """check the fix result with enhanced analysis
        
        Args:
            issue_desc
            fix_code
            execution_trace
            
        Returns:
            Dict[str, Any]:
            {
                "is_fixed": bool,                   
                "check_summary": str,               
                "fix_analysis": str,                
                "trace_analysis": str,              
                "efficiency_suggestions": List[str],
                "strategy_suggestions": List[str],  
                "overall_score": float,             
                
                "expert_assessment": {               
                    "confidence_level": str,         
                    "technical_depth_analysis": {},  
                    "cognitive_analysis": {}         
                },
                "execution_intelligence": {          
                    "strategy_effectiveness": {},    
                    "efficiency_analysis": {},       
                    "learning_patterns": {}          
                },
                "professional_recommendations": {    
                    "immediate_actions": [],         
                    "strategic_improvements": [],    
                    "learning_opportunities": []     
                },
                "risk_assessment": {                 
                    "production_risks": [],          
                    "technical_debt_impact": str,    
                    "regression_potential": str      
                },
                "quality_metrics": {                 
                    "detailed_scores": {},           
                    "score_justification": str       
                },
                "executive_summary": {               
                    "verdict": str,                  
                    "key_concerns": str,             
                    "success_criteria": str,         
                    "next_steps": str                
                }
            }
        """
        try:
            analysis_result = await self._call_model_for_enhanced_analysis(
                issue_desc, fix_code, context, execution_trace
            )
            return self._parse_enhanced_analysis_result(analysis_result)
        except Exception as e:
            return {
                "is_fixed": False,
                "check_summary": f"Error: {str(e)}",
                "fix_analysis": f"Error details: {str(e)}",
                "trace_analysis": "",
                "efficiency_suggestions": [],
                "strategy_suggestions": [],
                "overall_score": 0.0
            }
    
    async def _call_model_for_enhanced_analysis(
        self, 
        issue_desc: str, 
        fix_code: str,
        context: Any,
        execution_trace: Optional[ExecutionTrace]
    ) -> str:
        """call the model for enhanced analysis
        
        Args:
            issue_desc
            fix_code
            execution_trace
            
        Returns:
            str: the analysis result in JSON format
        """
        user_task = self._build_enhanced_prompt(issue_desc, fix_code, execution_trace)
        
        model_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": user_task},
        ]
        
        print("Enhanced checking fix task with trace analysis...")

        # Call the model with context support
        default_kwargs = {
            "model": settings.Claude_4_0_SONNET,
            "messages": model_messages,
            "stream": False,
            "temperature": 0.2,  # Lower temperature for accuracy
        }

        # Use get_client_with_kwargs to support context parameter overrides
        client, complete_kwargs = get_client_with_kwargs(context, default_kwargs)
        response = await client.chat_complete(**complete_kwargs)
        
        if response and response.choices and response.choices[0].message:
            analysis = response.choices[0].message.content
            if analysis:
                return analysis.strip()
        
        raise Exception("can't get analysis result from model response")
    
    def _build_enhanced_prompt(
        self, 
        issue_desc: str, 
        fix_code: str, 
        execution_trace: Optional[ExecutionTrace]
    ) -> str:
        
        expert_prompt = f"""
# 🎯 **SIADA PROJECT EXPERT & PR ANALYSIS SPECIALIST**

You are **Siada**, a **Senior Software Architect** and **AI Agent Execution Specialist** with 15+ years of experience in:

## **🔧 CORE EXPERTISE**
- **Enterprise Software Architecture**: Microservices, distributed systems, scalability patterns
- **Code Quality & Security**: SOLID principles, security vulnerabilities, performance optimization  
- **AI Agent Behavior Analysis**: Execution pattern recognition, strategy optimization, failure analysis
- **Pull Request Deep Review**: Impact assessment, regression analysis, integration concerns
- **Root Cause Investigation**: Multi-layer problem decomposition, systemic issue identification
- **Project Context Understanding**: Business logic, domain constraints, technical debt implications

---

## **🎯 MISSION: COMPREHENSIVE PR IMPACT ANALYSIS**

As a **project expert with deep codebase knowledge**, your mission is to:

1. **🔍 Perform forensic analysis** of the issue and proposed fix
2. **🧠 Identify cognitive biases** and thinking errors in the fix approach  
3. **⚡ Assess execution strategy effectiveness** from the trace data
4. **🎯 Provide actionable insights** for both immediate fixes and long-term improvements
5. **📊 Deliver a professional assessment** that prevents production incidents

---

## **📋 ANALYSIS FRAMEWORK**

### **🔍 PHASE 1: ISSUE FORENSICS & CONTEXT ANALYSIS**

#### **1.1 Multi-Dimensional Issue Decomposition**
- **🎯 Primary Problem**: Core functional failure or requirement gap
- **🔗 Dependency Chain**: What upstream/downstream components are affected?
- **👥 User Impact**: Which user journeys, APIs, or business processes break?
- **⏰ Timing Concerns**: Race conditions, async issues, state management problems
- **🔒 Security Implications**: Authentication, authorization, data exposure risks
- **📈 Performance Impact**: Scalability, memory usage, database query implications

#### **1.2 Business & Technical Context Assessment**
- **💼 Business Logic Constraints**: Domain rules, compliance requirements, workflow dependencies
- **🏗️ Architectural Patterns**: How does this fit with existing design patterns?
- **📚 Technical Debt**: What legacy constraints or shortcuts affect the solution space?
- **🔄 Integration Points**: APIs, databases, external services, event systems
- **🧪 Testing Strategy**: Unit, integration, end-to-end testing requirements

---

### **🧠 PHASE 2: COGNITIVE ANALYSIS & THINKING ERROR DETECTION**

#### **2.1 Fix Strategy Evaluation**
Analyze the **mental model** behind the fix:
- **🎯 Problem Framing**: Did the agent correctly identify the root cause vs symptoms?
- **🔍 Scope Definition**: Was the problem boundary appropriately defined?
- **⚖️ Solution Selection**: Why was this approach chosen over alternatives?
- **🔄 Implementation Strategy**: Was the execution sequence logical and safe?
- **✅ Validation Approach**: How was the fix verified and tested?

#### **2.2 Critical Thinking Error Categories**

**🚨 SCOPE & CONTEXT ERRORS**:
- **Tunnel Vision**: Focusing only on immediate symptoms
- **Context Blindness**: Missing project-specific constraints or patterns
- **Integration Ignorance**: Not considering downstream/upstream effects

**🧩 SOLUTION DESIGN ERRORS**:
- **Pattern Misapplication**: Using inappropriate design patterns
- **Over-Engineering**: Adding unnecessary complexity
- **Under-Engineering**: Missing essential robustness features

**🔍 VERIFICATION ERRORS**:
- **Testing Gaps**: Insufficient edge case coverage
- **Assumption Validation**: Not verifying critical assumptions
- **Regression Blindness**: Missing potential side effects

**⚡ EXECUTION ERRORS**:
- **Premature Optimization**: Focusing on performance before correctness
- **Error Handling Gaps**: Missing exception scenarios
- **State Management Issues**: Concurrency, persistence, consistency problems

---

### **📊 PHASE 3: EXECUTION TRACE DEEP ANALYSIS**

#### **3.1 Strategic Decision Analysis**
From the execution trace, evaluate:
- **🎯 Problem-Solving Strategy**: Was the approach systematic and thorough?
- **📚 Information Gathering**: Did the agent collect sufficient context?
- **🔄 Iterative Refinement**: How well did the agent adapt based on feedback?
- **⚡ Decision Speed vs Quality**: Balance between efficiency and thoroughness

#### **3.2 Tool Usage & Efficiency Assessment**
- **🛠️ Tool Selection Patterns**: Were the most appropriate tools chosen?
- **🔄 Call Sequence Optimization**: Could the workflow be more efficient?
- **❌ Error Recovery**: How well were failures handled and recovered?
- **💡 Missed Opportunities**: What better approaches were available?

---

## **📝 INPUT DATA**

### **🐛 ISSUE DESCRIPTION**
```
{issue_desc}
```

### **🔧 PROPOSED FIX (PR DIFF)**
```
{fix_code}
```

---
"""

        if execution_trace:
            trace_data = execution_trace.to_dict()
            trace_section = f"""
### **📈 EXECUTION TRACE DATA**
```json
{json.dumps(trace_data, indent=2, ensure_ascii=False)}
```

### **🔍 TRACE ANALYSIS REQUIREMENTS**

#### **3.3 Execution Pattern Analysis**
1. **🧠 Model Interaction Quality**:
   - **Prompt Engineering**: Were the prompts clear, specific, and context-rich?
   - **Response Utilization**: How effectively were model responses used?
   - **Conversation Flow**: Was the dialogue with the model productive?
   - **Token Efficiency**: Was the context window used optimally?

2. **🛠️ Tool Orchestration Analysis**:
   - **Tool Selection Logic**: Why were specific tools chosen at each step?
   - **Parameter Optimization**: Were tool parameters configured optimally?
   - **Error Handling**: How were tool failures managed and recovered?
   - **Workflow Efficiency**: Could the tool sequence be optimized?

3. **⏱️ Execution Timeline Analysis**:
   - **Critical Path**: What were the bottlenecks in the execution?
   - **Parallel Opportunities**: Could any operations be parallelized?
   - **Resource Utilization**: Was compute/memory used efficiently?
   - **Failure Points**: Where did the execution struggle or fail?

#### **3.4 Strategic Learning Analysis**
- **📚 Context Accumulation**: How did understanding evolve throughout execution?
- **🔄 Adaptation Patterns**: How well did the agent adapt to new information?
- **🎯 Goal Refinement**: Did the objectives become clearer over time?
- **💡 Insight Generation**: What key insights emerged during execution?

---
"""
            expert_prompt += trace_section

        output_requirements = """
## **📋 EXPERT-LEVEL OUTPUT REQUIREMENTS**

### **🎯 CHECK SUMMARY SPECIFICATION**

The `check_summary` is your **PROFESSIONAL ASSESSMENT** as a senior architect. It must be:

1. **🔍 Forensically Detailed**: Specific evidence-based analysis, not generic observations
2. **🧠 Cognitively Aware**: Explicit identification of thinking patterns and biases
3. **⚡ Strategically Insightful**: Clear understanding of why certain approaches were chosen
4. **🎯 Impact-Focused**: Concrete consequences and risk assessment
5. **💡 Solution-Oriented**: Actionable recommendations for improvement

**🏆 PROFESSIONAL CHECK SUMMARY FORMAT**:
```
"check_summary": "🔍 **EXPERT ANALYSIS**: [Specific technical assessment]. 🧠 **COGNITIVE PATTERN**: [Thinking approach analysis]. ⚠️ **CRITICAL GAPS**: [Missing considerations with evidence]. 🎯 **IMPACT ASSESSMENT**: [Concrete consequences]. 💡 **STRATEGIC RECOMMENDATION**: [Professional guidance for resolution]."
```

### **📊 REQUIRED EXPERT OUTPUT FORMAT**

```json
{
  "expert_assessment": {
    "is_fixed": false,
    "confidence_level": "High|Medium|Low",
    "check_summary": "🔍 **EXPERT ANALYSIS**: [Detailed technical assessment with specific evidence]. 🧠 **COGNITIVE PATTERN**: [Analysis of thinking approach and decision-making]. ⚠️ **CRITICAL GAPS**: [Specific missing considerations with concrete examples]. 🎯 **IMPACT ASSESSMENT**: [Detailed consequences and risk analysis]. 💡 **STRATEGIC RECOMMENDATION**: [Professional guidance for complete resolution].",
    "technical_depth_analysis": {
      "architecture_impact": "How this change affects the overall system architecture",
      "integration_concerns": "Specific integration points that may be affected",
      "performance_implications": "Detailed performance impact analysis",
      "security_considerations": "Security vulnerabilities or improvements",
      "maintainability_assessment": "Long-term maintenance and evolution concerns"
    },
    "cognitive_analysis": {
      "problem_framing_quality": "How well was the problem understood and framed",
      "solution_strategy_assessment": "Evaluation of the chosen solution approach",
      "decision_making_patterns": "Analysis of key decisions and their rationale",
      "blind_spots_identified": "Specific areas where awareness was lacking"
    }
  },
  "execution_intelligence": {
    "strategy_effectiveness": {
      "overall_approach": "Assessment of the high-level problem-solving strategy",
      "information_gathering": "Quality and completeness of context collection",
      "solution_development": "How the solution was developed and refined",
      "validation_strategy": "Approach to testing and verification"
    },
    "efficiency_analysis": {
      "resource_utilization": "How efficiently were computational resources used",
      "workflow_optimization": "Analysis of the execution workflow efficiency",
      "bottleneck_identification": "Specific performance bottlenecks identified",
      "improvement_opportunities": "Concrete opportunities for optimization"
    },
    "learning_patterns": {
      "adaptation_quality": "How well the agent adapted to new information",
      "insight_generation": "Quality of insights generated during execution",
      "error_recovery": "How effectively errors and failures were handled",
      "knowledge_integration": "How well different pieces of information were integrated"
    }
  },
  "professional_recommendations": {
    "immediate_actions": [
      "**CRITICAL**: [Urgent action needed to prevent issues]",
      "**IMPORTANT**: [Significant improvement with clear impact]",
      "**RECOMMENDED**: [Good practice improvement]"
    ],
    "strategic_improvements": [
      "**ARCHITECTURE**: [System-level improvements]",
      "**PROCESS**: [Development process enhancements]",
      "**TOOLING**: [Tool and automation improvements]"
    ],
    "learning_opportunities": [
      "**PATTERN RECOGNITION**: [Patterns to learn for future similar issues]",
      "**SKILL DEVELOPMENT**: [Specific skills to develop]",
      "**KNOWLEDGE GAPS**: [Areas requiring deeper understanding]"
    ]
  },
  "risk_assessment": {
    "production_risks": [
      {
        "risk_type": "Performance|Security|Functionality|Integration|Maintenance",
        "severity": "Critical|High|Medium|Low",
        "probability": "High|Medium|Low",
        "description": "Specific risk description with evidence",
        "mitigation": "Concrete steps to mitigate this risk"
      }
    ],
    "technical_debt_impact": "How this change affects technical debt",
    "regression_potential": "Likelihood and areas of potential regressions"
  },
  "quality_metrics": {
    "overall_score": 4.2,
    "detailed_scores": {
      "problem_understanding": 3.5,
      "solution_completeness": 4.0,
      "implementation_quality": 4.5,
      "testing_coverage": 3.0,
      "documentation_quality": 4.0,
      "execution_efficiency": 4.5,
      "strategic_thinking": 3.5
    },
    "score_justification": "Detailed explanation of scoring rationale with specific evidence"
  },
  "executive_summary": {
    "verdict": "**PROFESSIONAL VERDICT**: [Clear assessment of fix quality and completeness]",
    "key_concerns": "**PRIMARY CONCERNS**: [Top 3 most critical issues that must be addressed]",
    "success_criteria": "**SUCCESS CRITERIA**: [Specific criteria that must be met for this to be considered complete]",
    "next_steps": "**RECOMMENDED NEXT STEPS**: [Prioritized action plan for resolution]"
  }
}
```

### **🎯 EXPERT SCORING METHODOLOGY**

**📊 SCORING CRITERIA** (0.0 - 10.0 scale):

- **🔴 0-2**: **Critical Failure** - Fundamental misunderstanding, introduces new problems
- **🟠 3-4**: **Significant Issues** - Partially addresses problem but with major gaps
- **🟡 5-6**: **Adequate with Concerns** - Addresses main issue but missing important aspects
- **🟢 7-8**: **Good Quality** - Solid solution with minor improvements needed
- **🔵 9-10**: **Exceptional** - Comprehensive, robust, well-architected solution

### **⚠️ CRITICAL ASSESSMENT RULES**

1. **🚨 ALWAYS set `is_fixed: false`** if ANY of these exist:
   - Incomplete root cause resolution
   - Missing critical edge cases or error handling
   - Performance degradation or scalability concerns
   - Security vulnerabilities introduced or not addressed
   - Integration problems with existing systems
   - Insufficient testing or validation
   - Technical debt increase without justification

2. **🎯 PROFESSIONAL STANDARDS**:
   - **Evidence-Based**: Every claim must be supported by specific evidence
   - **Risk-Aware**: Consider production impact and failure scenarios
   - **Context-Sensitive**: Account for project-specific constraints and patterns
   - **Future-Oriented**: Consider long-term maintenance and evolution

3. **💡 ACTIONABLE INSIGHTS**:
   - Provide specific, implementable recommendations
   - Prioritize suggestions by impact and effort
   - Include concrete examples and code patterns where helpful
   - Focus on both immediate fixes and strategic improvements

---

## **🎯 FINAL DIRECTIVE**

Conduct a **forensic-level analysis** as a senior architect would during a critical production incident review. Your assessment will be used to:

1. **🚨 Prevent production incidents** through thorough risk identification
2. **📈 Improve development processes** through strategic insights
3. **🧠 Enhance AI agent capabilities** through execution pattern analysis
4. **🎯 Guide future similar issues** through pattern recognition

**Be thorough, be specific, be professional. Lives depend on the software we build.**
"""

        return expert_prompt + output_requirements
    
    def _parse_enhanced_analysis_result(self, analysis_result: str) -> Dict[str, Any]:
        """
        Args:
            analysis_result
            
        Returns:
            Dict[str, Any]
        """
        try:
            if not analysis_result or not analysis_result.strip():
                raise ValueError("the analysis result is empty")
            
            json_content = analysis_result.strip()
            
            if '```json' in json_content:
                json_start = json_content.find('```json')+len('```json')
                json_end = json_content.rfind('```')
                
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_content = json_content[json_start:json_end]

            if not json_content:
                raise ValueError("the extracted JSON content is empty")
            
            parsed_json = json.loads(json_content)
            
            expert_assessment = parsed_json.get("expert_assessment", {})
            execution_intelligence = parsed_json.get("execution_intelligence", {})
            professional_recommendations = parsed_json.get("professional_recommendations", {})
            risk_assessment = parsed_json.get("risk_assessment", {})
            quality_metrics = parsed_json.get("quality_metrics", {})
            executive_summary = parsed_json.get("executive_summary", {})
            
            result = {
                "is_fixed": expert_assessment.get("is_fixed", False),
                "check_summary": expert_assessment.get("check_summary", "未提供专家分析摘要"),
                "fix_analysis": expert_assessment.get("technical_depth_analysis", {}).get("architecture_impact", "未提供详细分析"),
                "trace_analysis": execution_intelligence.get("strategy_effectiveness", {}).get("overall_approach", "未提供轨迹分析"),
                "efficiency_suggestions": professional_recommendations.get("immediate_actions", []),
                "strategy_suggestions": professional_recommendations.get("strategic_improvements", []),
                "overall_score": quality_metrics.get("overall_score", 0.0),
                
                "expert_assessment": {
                    "confidence_level": expert_assessment.get("confidence_level", "Medium"),
                    "technical_depth_analysis": expert_assessment.get("technical_depth_analysis", {}),
                    "cognitive_analysis": expert_assessment.get("cognitive_analysis", {})
                },
                
                "execution_intelligence": {
                    "strategy_effectiveness": execution_intelligence.get("strategy_effectiveness", {}),
                    "efficiency_analysis": execution_intelligence.get("efficiency_analysis", {}),
                    "learning_patterns": execution_intelligence.get("learning_patterns", {})
                },
                
                "professional_recommendations": {
                    "immediate_actions": professional_recommendations.get("immediate_actions", []),
                    "strategic_improvements": professional_recommendations.get("strategic_improvements", []),
                    "learning_opportunities": professional_recommendations.get("learning_opportunities", [])
                },
                
                "risk_assessment": {
                    "production_risks": risk_assessment.get("production_risks", []),
                    "technical_debt_impact": risk_assessment.get("technical_debt_impact", "未评估"),
                    "regression_potential": risk_assessment.get("regression_potential", "未评估")
                },
                
                "quality_metrics": {
                    "detailed_scores": quality_metrics.get("detailed_scores", {}),
                    "score_justification": quality_metrics.get("score_justification", "未提供评分说明")
                },
                
                "executive_summary": {
                    "verdict": executive_summary.get("verdict", "未提供专业判断"),
                    "key_concerns": executive_summary.get("key_concerns", "未识别关键问题"),
                    "success_criteria": executive_summary.get("success_criteria", "未定义成功标准"),
                    "next_steps": executive_summary.get("next_steps", "未提供后续步骤")
                },
                
                "score_breakdown": quality_metrics.get("detailed_scores", {}),
                "overall_summary": executive_summary.get("verdict", "未提供综合评估")
            }
            
            return result
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            raise ValueError(
                f"Failed to parse enhanced analysis result: {str(e)}. "
                "Please ensure the model output is in the correct JSON format."
            )
