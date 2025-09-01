"""
Issue Type Checker
For determining whether a problem description is a complex feature request or a specific bug fix
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, Union, Optional, TYPE_CHECKING

from openai.types.chat import ChatCompletionMessageParam

if TYPE_CHECKING:
    from siada.agent_hub.coder.tracing.bug_fix_trace_collector import BugFixTraceCollector

from siada.provider.client_factory import get_client_with_kwargs
from siada.foundation.setting import settings
from siada.services.fix_result_check import FixResultChecker

logger = logging.getLogger(__name__)

class IssueTypeChecker(FixResultChecker):
    """Issue Type Checker that inherits from FixResultChecker to determine if an issue is a feature request or bug fix"""

    async def analyze_issue_type(self, issue_desc: str, context: Any) -> Dict[str, Any]:
        """
        Analyze the type of issue description
        
        Args:
            issue_desc: Issue description
            context: Contains provider and other necessary information
            
        Returns:
            Dict[str, Any]:
            {
                "issue_type": str,  # "feature_request" or "bug_fix"
                "complexity": str,  # "simple", "medium", "complex"
                "confidence": float,  # confidence score 0.0-1.0
                "analysis": str,    # detailed analysis
                "key_indicators": List[str]  # key indicators
                "project_type": str,  # special project type if applicable
            }
        """
        try:
            analysis_result = await self._call_model_for_issue_analysis(issue_desc, context)
            return self._parse_issue_analysis_result(analysis_result)
        except Exception as e:
            logger.error(f"Issue type analysis failed: {e}", exc_info=True)
            return {
                "issue_type": "unknown",
                "complexity": "unknown",
                "confidence": 0.0,
                "analysis": f"Analysis process error: {str(e)}",
                "key_indicators": [],
                "project_type": "unknown"
            }

    async def analyze_project_type(self, issue_desc: str, context: Any, trace_collector: Optional["BugFixTraceCollector"] = None) -> Dict[str, Any]:
        """
        Analyze which project/framework this issue belongs to
        
        Args:
            issue_desc: Issue description
            context: Contains provider and other necessary information
            trace_collector: Optional trace collector for recording analysis process
            
        Returns:
            Dict[str, Any]: Project type analysis result
        """
        try:
            analysis_result = await self._call_model_for_project_analysis(issue_desc, context)
            result = self._parse_project_analysis_result(analysis_result)
            
            # Record trace using the encapsulated function
            self._record_project_analysis_trace(trace_collector, issue_desc, result)
            
            return result
        except Exception as e:
            logger.error(f"Project type analysis failed: {e}", exc_info=True)
            error_result = {
                "project_type": "unknown",
                "confidence": 0.0,
                "analysis": f"Project analysis error: {str(e)}",
                "key_indicators": []
            }
            
            # Record error trace using the encapsulated function
            self._record_project_analysis_trace(trace_collector, issue_desc, error_result)
            
            return error_result
    
    async def _call_model_for_issue_analysis(self, issue_desc: str, context: Any) -> str:
        """Call model for issue type analysis"""
        
        user_task = self._build_issue_analysis_prompt(issue_desc)
        
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
        
        if response and response.choices and response.choices[0].message:
            analysis = response.choices[0].message.content
            if analysis:
                return analysis.strip()
        
        raise Exception("Cannot get analysis result from model response")
    
    async def _call_model_for_project_analysis(self, issue_desc: str, context: Any) -> str:
        """Call model for project type analysis"""
        
        user_task = self._build_project_analysis_prompt(issue_desc)
        print("project domain classification prompt:", user_task)
        model_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": user_task},
        ]

        # Call the model
        default_kwargs = {
            "model": settings.Claude_4_0_SONNET,
            "messages": model_messages,
            "stream": False,
            "temperature": 0.2,
        }

        client, complete_kwargs = get_client_with_kwargs(context, default_kwargs)
        response = await client.chat_complete(**complete_kwargs)
        
        if response and response.choices and response.choices[0].message:
            analysis = response.choices[0].message.content
            if analysis:
                return analysis.strip()
        
        raise Exception("Cannot get project analysis result from model response")
    
    def _build_project_analysis_prompt(self, issue_desc: str) -> str:
        """Build prompt for project type analysis"""
        return f"""
You are a **Software Project Analysis Expert** specializing in identifying which type of Python framework or library category an issue belongs to.
Please analyze the following issue description to determine which project category it relates to.

## Project Category Classification Framework

### 1. Web Development Framework Category
**Strong Web Framework Indicators**:
    - Admin interface concepts: "admin", "readonly", "display_for_field"
    - Web-specific modules: "contrib.admin", "contrib.sessions", "core"
    - ORM components: "QuerySet", "Model", "Field", "JSONField"
    - Web concepts: "migration", "template", "view", "middleware"
    - HTTP terms: "HTTP", "request", "response", "URL routing", "session"
    - Web file structure: "settings.py", "models.py", "views.py"
    - Routing concepts: "app.route", lightweight web framework patterns

### 2. Data Visualization Category
**Strong Visualization Indicators**:
    - Plotting concepts: "figure", "plot", "DPI", "canvas", "backend"
    - Visualization terms: "graph", "chart", "axis", "legend", "colormap", "seaborn"
    - Graphics modules: "pyplot", plotting backends
    - Graphics issues: "rendering", "display", "visual", "image"
    - Platform-specific: "MacOSX backend", "GUI", "interactive plots"
    - File formats: "PNG", "SVG", "PDF" in plotting context
    - Statistical plotting: distribution plots, heatmaps

### 3. Data Science Category
**Strong Data Science Indicators**:
    - Machine learning terms: "classifier", "regression", "model", "fit", "predict"
    - Data science: "dataset", "features", "training", "validation"
    - ML algorithms: "SVM", "random forest", "clustering", "preprocessing"
    - Scientific computing: numerical computations, data analysis

### 4. Development Tools Category
**Strong Development Tools Indicators**:
    - Code quality: linting, style checking, code analysis
    - Testing frameworks: test runners, assertion frameworks
    - Documentation: documentation generation, "rst", "docs", "build"
    - Development workflow: CI/CD, build tools, development utilities

### 5. Core Libraries Category
**Strong Core Library Indicators**:
    - Mathematical concepts: "symbolic", "equation", "algebra", "calculus"
    - Mathematical operations: "solve", "integrate", "differentiate", "simplify"
    - Mathematical objects: "Symbol", "Matrix", "expression"
    - HTTP client functionality: network requests, authentication, sessions
    - Fundamental utilities: core Python ecosystem libraries

## Analysis Task

**Issue Description**:
    {issue_desc}

## Output Requirements

Please return the analysis result in JSON format:

    ```json
    {{
        "project_analysis": {{
        "project_type": "web_framework|data_visualization|data_science|development_tools|core_libraries",
        "confidence": 0.92,
        "analysis": "Detailed explanation of why this issue belongs to this category",
        "key_indicators": [
            "indicator1: explanation",
            "indicator2: explanation"
        ],
        "framework_evidence": {{
            "module_references": ["List of specific modules mentioned"],
            "technical_terms": ["Category-specific technical terms"],
            "code_patterns": ["Specific code patterns or APIs mentioned"]
        }},
        "alternative_possibilities": [
            "If confidence < 0.9, list other possible categories"
        ]
        }}
    }}
    ```

## Classification Rules

    **High Confidence (>0.9)**: Clear module references, specific technical terms, unambiguous context
    **Medium Confidence (0.7-0.9)**: Some specific indicators but could potentially be another category
    **Low Confidence (<0.7)**: Generic terms that could apply to multiple categories

    **Priority Order**:
    1. Explicit module imports or paths → High confidence
    2. Category-specific technical terminology → Medium to high confidence
    3. Domain-specific concepts (web dev, plotting, math, tools) → Medium confidence
    4. Generic programming terms → Low confidence

Please provide detailed reasoning based on specific evidence from the issue description.
        """
    
    def _parse_project_analysis_result(self, analysis_result: str) -> Dict[str, Any]:
        """Parse the project analysis result from model response"""
        try:
            if not analysis_result or not analysis_result.strip():
                raise ValueError("Project analysis result is empty")
            
            json_content = analysis_result.strip()
            
            # Extract JSON from markdown code blocks if present
            if '```json' in json_content:
                json_start = json_content.find('```json') + len('```json')
                json_end = json_content.rfind('```')
                
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_content = json_content[json_start:json_end]

            if not json_content:
                raise ValueError("Extracted project JSON content is empty")
            
            parsed_json = json.loads(json_content)
            project_analysis = parsed_json.get("project_analysis", {})
            
            result = {
                "project_type": project_analysis.get("project_type", "unknown"),
                "confidence": project_analysis.get("confidence", 0.0),
                "analysis": project_analysis.get("analysis", "No analysis provided"),
                "key_indicators": project_analysis.get("key_indicators", []),
                "framework_evidence": project_analysis.get("framework_evidence", {}),
                "alternative_possibilities": project_analysis.get("alternative_possibilities", []),
                "raw_response": analysis_result
            }
            
            return result
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Fallback to simple keyword analysis
            raise Exception(f"Project analysis parsing error: {str(e)}")
    
    
    def _build_issue_analysis_prompt(self, issue_desc: str) -> str:
        """Build prompt for issue type analysis"""
        return f"""
        You are a **Software Engineering Expert** specializing in analyzing issue types in software development.
        Please analyze the following issue description to determine whether it's a feature request or bug fix, and assess its complexity level.

        ## Analysis Framework

        ### 1. Issue Type Classification Criteria

        **Bug Fix Characteristics**:
        - Describes erroneous behavior or exceptions in software
        - Contains keywords like "error", "exception", "crash", "failure", "broken"
        - Describes discrepancy between expected and actual behavior
        - Involves correction of existing functionality
        - Contains error messages, exception stacks, or logs
        - Describes reproduction steps
        - Uses phrases like "doesn't work", "fails to", "incorrect behavior"

        **Feature Request Characteristics**:
        - Describes new functionality or features
        - Uses keywords like "add", "implement", "support", "enhance", "allow"
        - Describes user stories or use cases
        - Involves new APIs, new interfaces, or new workflows
        - Contains feature specifications
        - Describes expected new behavior
        - Uses phrases like "would like to", "should be able to", "new feature"

        ### 2. Complexity Assessment Criteria

        **Simple**:
        - Single file or few files modification
        - Straightforward logic
        - No architectural changes
        - Small impact scope
        - Clear implementation path

        **Medium**:
        - Multiple files or modules modification
        - Requires some design consideration
        - May affect related functionality
        - Moderate testing required
        - Some integration complexity

        **Complex**:
        - Involves multiple systems or many modules
        - Requires architectural design or refactoring
        - Wide-ranging impact
        - Extensive testing and validation required
        - Cross-cutting concerns or major design changes

        ### 3. Key Indicator Identification

        Please identify key words and phrases in the issue description that help determine the issue type:
        - Bug-related: error, exception, crash, fail, broken, incorrect, wrong, bug, issue, problem
        - Feature-related: add, implement, support, enhance, feature, new, allow, enable, provide
        - Complexity-related: refactor, redesign, architecture, multiple, complex, system-wide, major

        ## Analysis Task

        **Issue Description**:
        {issue_desc}

        ## Output Requirements

        Please return the analysis result in JSON format:

        ```json
        {{
          "issue_analysis": {{
            "issue_type": "feature_request|bug_fix",
            "complexity": "simple|medium|complex",
            "confidence": 0.85,
            "analysis": "Detailed analysis explaining why this is classified as this type and complexity level",
            "key_indicators": [
              "keyword1: explanation",
              "keyword2: explanation",
              "feature_description: explanation"
            ],
            "reasoning": {{
              "type_reasoning": "Specific reasoning for issue type determination",
              "complexity_reasoning": "Specific reasoning for complexity assessment",
              "evidence": [
                "Evidence supporting the classification 1",
                "Evidence supporting the classification 2"
              ]
            }},
            "decision_factors": {{
              "primary_indicators": ["Most important indicators that led to this classification"],
              "secondary_indicators": ["Supporting indicators"],
              "ambiguous_aspects": ["Any unclear or conflicting aspects"]
            }}
          }}
        }}
        ```

        ## Classification Guidelines

        **Priority Decision Rules**:
        1. If the description mentions existing functionality not working correctly → **Bug Fix**
        2. If the description asks for new capabilities or features → **Feature Request**
        3. If both aspects are present, classify based on the primary intent
        4. Consider the overall tone and context of the description

        **Complexity Assessment Rules**:
        1. Count the number of systems/components mentioned
        2. Assess the scope of changes required
        3. Consider testing and validation complexity
        4. Evaluate potential impact on existing functionality

        Please provide a thorough analysis with high confidence levels based on clear evidence from the issue description.
        """
    
    def _parse_issue_analysis_result(self, analysis_result: str) -> Dict[str, Any]:
        """Parse the issue analysis result from model response"""
        try:
            if not analysis_result or not analysis_result.strip():
                raise ValueError("Analysis result is empty")
            
            json_content = analysis_result.strip()
            
            # Extract JSON from markdown code blocks if present
            if '```json' in json_content:
                json_start = json_content.find('```json') + len('```json')
                json_end = json_content.rfind('```')
                
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_content = json_content[json_start:json_end]

            if not json_content:
                raise ValueError("Extracted JSON content is empty")
            
            parsed_json = json.loads(json_content)
            
            issue_analysis = parsed_json.get("issue_analysis", {})
            
            result = {
                "issue_type": issue_analysis.get("issue_type", "unknown"),
                "complexity": issue_analysis.get("complexity", "unknown"),
                "confidence": issue_analysis.get("confidence", 0.0),
                "analysis": issue_analysis.get("analysis", "No analysis provided"),
                "key_indicators": issue_analysis.get("key_indicators", []),
                "reasoning": issue_analysis.get("reasoning", {}),
                "decision_factors": issue_analysis.get("decision_factors", {}),
                "raw_response": analysis_result
            }
            
            return result
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Fallback to text analysis if JSON parsing fails
            return self._fallback_text_analysis(analysis_result, str(e))
    
    def _fallback_text_analysis(self, analysis_result: str, error_msg: str) -> Dict[str, Any]:
        """Fallback text analysis when JSON parsing fails"""
        
        analysis_lower = analysis_result.lower()
        
        # Simple keyword-based classification
        bug_keywords = ['error', 'exception', 'crash', 'fail', 'broken', 'incorrect', 'wrong', 'bug', 'issue', 'problem']
        feature_keywords = ['add', 'implement', 'support', 'enhance', 'feature', 'new', 'allow', 'enable', 'provide']
        
        bug_count = sum(1 for keyword in bug_keywords if keyword in analysis_lower)
        feature_count = sum(1 for keyword in feature_keywords if keyword in analysis_lower)
        
        if bug_count > feature_count:
            issue_type = "bug_fix"
            confidence = min(0.7, bug_count * 0.1 + 0.3)
        elif feature_count > bug_count:
            issue_type = "feature_request"
            confidence = min(0.7, feature_count * 0.1 + 0.3)
        else:
            issue_type = "unknown"
            confidence = 0.3
        
        # Simple complexity assessment based on text length and keywords
        complexity_keywords = ['refactor', 'redesign', 'architecture', 'multiple', 'complex', 'system']
        complexity_count = sum(1 for keyword in complexity_keywords if keyword in analysis_lower)
        
        if len(analysis_result) > 500 or complexity_count >= 3:
            complexity = "complex"
        elif len(analysis_result) > 200 or complexity_count >= 1:
            complexity = "medium"
        else:
            complexity = "simple"
        
        return {
            "issue_type": issue_type,
            "complexity": complexity,
            "confidence": confidence,
            "analysis": f"[JSON Parsing Failed: {error_msg}] Fallback analysis based on keyword detection",
            "key_indicators": [f"Bug keywords: {bug_count}", f"Feature keywords: {feature_count}"],
            "reasoning": {"fallback": True, "error": error_msg},
            "decision_factors": {"method": "keyword_based_fallback"},
            "raw_response": analysis_result
        }
    
    def _record_project_analysis_trace(self, trace_collector:BugFixTraceCollector, issue_desc: str, result: Dict[str, Any]) -> None:
        """
        Record project analysis trace information
        
        Args:
            trace_collector: Optional trace collector 
            issue_desc: Issue description
            result: Analysis result
        """
        if not trace_collector:
            return
            
        prompt = self._build_project_analysis_prompt(issue_desc)
        trace_collector.record_project_analysis(
            prompt=prompt,
            user_input=issue_desc,
            result=result
        )
