import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.coder.tracing.logger_tracing_processor import LoggerTracingProcessor

from agents.tracing import TracingProcessor

@dataclass
class ProjectAnalysisTrace:
    """ Identify the problem domain """
    prompt: str = ""
    user_input: str = ""
    classification_result: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationTrace:
    """Optimize problem description"""
    prompt: str = ""
    original_input: str = ""
    optimized_result: str = ""
    project_type: str = ""


@dataclass
class ToolCall:
    tool_name: str
    input_args: Dict[str, Any]
    output_result: Any


@dataclass
class ModelCall:
    input_messages: List[Dict[str, Any]]
    output_message: Dict[str, Any]
    model_name: str = ""
    usage: Optional[Dict[str, Any]] = None


@dataclass
class RunRoundTrace:
    """One run round of bug fix"""
    round_number: int
    input_list: List[Dict[str, Any]]
    model_calls: List[ModelCall] = field(default_factory=list)
    tool_calls: List[ToolCall] = field(default_factory=list)
    final_output: str = ""


@dataclass
class CheckerTrace:
    """Checker run trace"""
    prompt: str = ""
    user_input: str = ""
    check_summary: str = ""
    feedback_message: Dict[str, Any] = field(default_factory=dict)
    should_break: bool = False


@dataclass
class PatchSelectionTrace:
    input_patches: List[str] = field(default_factory=list)
    selection_prompt: str = ""
    model_calls: List[ModelCall] = field(default_factory=list)
    tool_calls: List[ToolCall] = field(default_factory=list)
    selected_patch_index: int = -1
    reasoning: str = ""
    application_success: bool = False


@dataclass
class BugFixTraceSession:
    session_id: str
    original_issue: str = ""
    execution_overview: Optional[str] =""
    classify: Optional[ProjectAnalysisTrace] = None
    issue_optimize: Optional[OptimizationTrace] = None
    bug_fix_rounds: List[RunRoundTrace] = field(default_factory=list)
    check_rounds: List[CheckerTrace] = field(default_factory=list)
    patch_selection: Optional[PatchSelectionTrace] = None
    final_result: str = ""
    success: bool = False
    error_message: str = ""

@dataclass
class BugFixTraceSessionOld:
    session_id: str
    original_issue: str = ""
    execution_overview: Optional[str] =""
    project_domain_classification: Optional[ProjectAnalysisTrace] = None
    issue_description_optimization: Optional[OptimizationTrace] = None
    bug_fix_run_rounds: List[RunRoundTrace] = field(default_factory=list)
    checker_traces: List[CheckerTrace] = field(default_factory=list)
    patch_selection: Optional[PatchSelectionTrace] = None
    final_result: str = ""
    success: bool = False
    error_message: str = ""

@dataclass
class HistoryItem:
    execution_stage: str="" 
    content: dict=field(default_factory=dict)

@dataclass
class OutputData:
    trajectory: BugFixTraceSession
    history: List[HistoryItem] = field(default_factory=list)
    info: dict=field(default_factory=dict)
    replay_config: str=""
    environment: str=""

class BugFixTraceCollector(TracingProcessor):    
    def __init__(self, session_id: Optional[str] = None, output_dir: str = "bug_fix_traces", **kwargs):

        self.session_id = session_id or self._generate_session_id()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.trace_session = BugFixTraceSession(session_id=self.session_id)
        
        # trace state 
        self.current_round = 0
        self.current_run_round_trace = None
        self.is_in_patch_selection = False
        self.current_model_call_start_time = None
        self.current_tool_call_start_time = None
        
        self.agent_name = "siada"
        self.submission_diff = ""
        self.exit_status = ""
        
    
    def _generate_session_id(self) -> str:
        return f"bugfix_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(self) % 10000:04d}"
    
    def start_session(self, original_issue: str) -> None:
        self.trace_session.original_issue = original_issue
    
    def record_project_analysis(self, prompt: str, user_input: str, result: Dict[str, Any]) -> None:
        self.trace_session.classify = ProjectAnalysisTrace(
            prompt=prompt,
            user_input=user_input,
            classification_result=result
        )
    
    def record_optimization(self, prompt: str, original_input: str, 
                          optimized_result: str, project_type: str) -> None:
        self.trace_session.issue_optimize = OptimizationTrace(
            prompt=prompt,
            original_input=original_input,
            optimized_result=optimized_result,
            project_type=project_type
        )
    
    def start_run_round(self, input_list: List[Dict[str, Any]]) -> None:
        self.current_round += 1
        round_trace = RunRoundTrace(
            round_number=self.current_round,
            input_list=input_list
        )
        self.trace_session.bug_fix_rounds.append(round_trace)
    
    def start_model_call(self) -> None:
        pass
    
    def end_model_call(self, input_messages: List[Dict[str, Any]], 
                      output_message: Dict[str, Any], model_name: str = "", 
                      usage: Optional[Dict[str, Any]] = None) -> None:
        if not self.trace_session.bug_fix_rounds:
            return
        
        model_call = ModelCall(
            input_messages=input_messages,
            output_message=output_message,
            model_name=model_name
        )
        
        self.trace_session.bug_fix_rounds[-1].model_calls.append(model_call)
    
    def start_tool_call(self) -> None:
        pass
    
    def end_tool_call(self, tool_name: str, input_args: Dict[str, Any], 
                     output_result: Any) -> None:
        if not self.trace_session.bug_fix_rounds:
            return
        
        tool_call = ToolCall(
            tool_name=tool_name,
            input_args=input_args,
            output_result=output_result
        )
        
        self.trace_session.bug_fix_rounds[-1].tool_calls.append(tool_call)
    
    def end_run_round(self, final_output: str) -> None:
        if self.trace_session.bug_fix_rounds:
            self.trace_session.bug_fix_rounds[-1].final_output = final_output
    
    def record_checker_trace(self, prompt: str, user_input: str, check_summary: str,
                           feedback_message: Dict[str, Any], should_break: bool) -> None:
        checker_trace = CheckerTrace(
            prompt=prompt,
            user_input=user_input,
            check_summary=check_summary,
            feedback_message=feedback_message,
            should_break=should_break
        )
        self.trace_session.check_rounds.append(checker_trace)
    
    def start_patch_selection(self, patches: List[str], selection_prompt: str) -> None:
        self.is_in_patch_selection = True  
        self.trace_session.patch_selection = PatchSelectionTrace(
            input_patches=patches,
            selection_prompt=selection_prompt
        )
    
    def record_patch_selection_model_call(self, input_messages: List[Dict[str, Any]], 
                                        output_message: Dict[str, Any], model_name: str = "",
                                        usage: Optional[Dict[str, Any]] = None) -> None:
        if not self.trace_session.patch_selection:
            return
            
        model_call = ModelCall(
            input_messages=input_messages,
            output_message=output_message,
            model_name=model_name,
            # usage=usage
        )
        self.trace_session.patch_selection.model_calls.append(model_call)
    
    def record_patch_selection_tool_call(self, tool_name: str, input_args: Dict[str, Any],
                                       output_result: Any) -> None:
        if not self.trace_session.patch_selection:
            return
            
        tool_call = ToolCall(
            tool_name=tool_name,
            input_args=input_args,
            output_result=output_result
        )
        self.trace_session.patch_selection.tool_calls.append(tool_call)
    
    def end_patch_selection(self, selected_patch_index: int, reasoning: str, 
                          application_success: bool) -> None:
        if self.trace_session.patch_selection:
            self.trace_session.patch_selection.selected_patch_index = selected_patch_index
            self.trace_session.patch_selection.reasoning = reasoning
            self.trace_session.patch_selection.application_success = application_success
        

        self.is_in_patch_selection = False
    
    def end_session(self, final_result: str, success: bool, error_message: str = "") -> None:
        self.trace_session.final_result = final_result
        self.trace_session.success = success
        self.trace_session.error_message = error_message
    
    def set_agent_name(self, agent_name: str) -> None:
        self.agent_name = agent_name

    def set_submission_diff(self, diff_content: str) -> None:
        self.submission_diff = diff_content

    def get_agent_name(self) -> str:
        return self.agent_name

    def get_submission_diff(self) -> str:
        return self.submission_diff
    
    def collect_submission_diff(self, context) -> None:
        try:
            from siada.foundation.tools.get_git_diff import GitDiffUtil
            diff_content = GitDiffUtil.get_git_diff(context.root_dir)
            self.set_submission_diff(diff_content)
        except Exception as e:
            print(f"Failed to collect submission diff: {e}")
            self.set_submission_diff("")
    
    
    def on_trace_start(self, trace) -> None:
        pass
    
    def on_trace_end(self, trace) -> None:
        pass
    
    def on_span_start(self, span) -> None:
        
        span_type = span.span_data.type
        
        if span_type == "generation":
            if not self.is_in_patch_selection and self.trace_session.bug_fix_rounds:
                pass  
                
        elif span_type == "function":
            pass
            
    def on_span_end(self, span) -> None:
        
        span_type = span.span_data.type
        data = span.span_data
        
        if span_type == "generation":
            self._record_model_call_from_span(span)
            
        elif span_type == "function":
            self._record_tool_call_from_span(span)
    
    def shutdown(self) -> None:
        pass
    
    def force_flush(self) -> None:
        pass
    
    def _record_model_call_from_span(self, span) -> None:
        data = span.span_data
        
        input_messages = []
        if hasattr(data, 'input') and data.input:
            input_messages = [
                {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                for msg in data.input
            ]
        
        output_message = {}
        if hasattr(data, 'output') and data.output:
            if isinstance(data.output, list) and len(data.output) > 0:
                output_item = data.output[0]
                if hasattr(output_item, 'content'):
                    output_message = {"role": "assistant", "content": str(output_item.content)}
                else:
                    output_message = {"role": "assistant", "content": str(output_item)}
            else:
                output_message = {"role": "assistant", "content": str(data.output)}
        
        usage = None
        if hasattr(data, 'usage') and data.usage:
            usage = {
                "input_tokens": getattr(data.usage, 'input_tokens', 0),
                "output_tokens": getattr(data.usage, 'output_tokens', 0),
                "total_tokens": getattr(data.usage, 'total_tokens', 0)
            }
        
        model_name = getattr(data, 'model', '') or ''
        
        model_call = ModelCall(
            input_messages=input_messages,
            output_message=output_message,
            model_name=model_name,
            # usage=usage
        )
        
        if self.is_in_patch_selection and self.trace_session.patch_selection:
            self.trace_session.patch_selection.model_calls.append(model_call)
        elif self.trace_session.bug_fix_rounds:
            self.trace_session.bug_fix_rounds[-1].model_calls.append(model_call)
    
    def _record_tool_call_from_span(self, span) -> None:
        data = span.span_data
        
        tool_name = getattr(data, 'name', '') or 'unknown'
        
        input_args = {}
        if hasattr(data, 'input') and data.input:
            try:
                if isinstance(data.input, dict):
                    input_args = data.input
                else:
                    input_args = {"raw_input": str(data.input)}
            except Exception:
                input_args = {"raw_input": str(data.input)}
        
        output_result = None
        if hasattr(data, 'output'):
            output_result = data.output
        
        tool_call = ToolCall(
            tool_name=tool_name,
            input_args=input_args,
            output_result=output_result
        )
        
        if self.is_in_patch_selection and self.trace_session.patch_selection:
            self.trace_session.patch_selection.tool_calls.append(tool_call)
        elif self.trace_session.bug_fix_rounds:
            self.trace_session.bug_fix_rounds[-1].tool_calls.append(tool_call)
    
    def export_to_json(self, filename: Optional[str] = None) -> str:
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"bugfix_trace_{self.session_id}_{timestamp}.json"
        
        output:OutputData = self.formatter_export_data(self.trace_session)

        filepath = self.output_dir / filename
        
        trace_dict = asdict(output)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(trace_dict, f, indent=2, ensure_ascii=False)
        
        return str(filepath)
    
    def export_to_json_v2(self, filename: Optional[str] = None) -> str:
        """
        {
            "trajectory": { BugFixTraceSession },
            "info": {
                "agent": "siada",
                "submission": "diff内容"
            }
        }
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"bugfix_trace_v2_{self.session_id}_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        export_data = {
            "trajectory": asdict(self.trace_session),
            "info": {
                "agent": self.agent_name,
                "submission": self.submission_diff
            }
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        return str(filepath)
    
    def get_summary(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "original_issue": self.trace_session.original_issue,
            "total_rounds": len(self.trace_session.bug_fix_rounds),
            "total_model_calls": sum(len(round_trace.model_calls) for round_trace in self.trace_session.bug_fix_rounds),
            "total_tool_calls": sum(len(round_trace.tool_calls) for round_trace in self.trace_session.bug_fix_rounds),
            "checker_runs": len(self.trace_session.check_rounds),
            "patch_selection_used": self.trace_session.patch_selection is not None,
            "success": self.trace_session.success,
            "final_result": self.trace_session.final_result[:200] + "..." if len(self.trace_session.final_result) > 200 else self.trace_session.final_result
        }
    
    def load_from_json(self, filepath: Union[str, Path]) -> None:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        trace_session = BugFixTraceSession(
            session_id=data.get('session_id', ''),
            original_issue=data.get('original_issue', ''),
            final_result=data.get('final_result', ''),
            success=data.get('success', False),
            error_message=data.get('error_message', '')
        )
        
        if data.get('classify'):
            trace_session.classify = ProjectAnalysisTrace(**data['classify'])
        elif data.get('project_analysis'):  
            trace_session.classify = ProjectAnalysisTrace(**data['project_analysis'])
        
        if data.get('issue_optimize'):
            trace_session.issue_optimize = OptimizationTrace(**data['issue_optimize'])
        elif data.get('optimization'): 
            trace_session.issue_optimize = OptimizationTrace(**data['optimization'])
        
        if data.get('bug_fix_rounds'):
            for round_data in data['bug_fix_rounds']:
                round_trace = RunRoundTrace(
                    round_number=round_data.get('round_number', 0),
                    input_list=round_data.get('input_list', []),
                    final_output=round_data.get('final_output', '')
                )
                
                for mc_data in round_data.get('model_calls', []):
                    model_call = ModelCall(**mc_data)
                    round_trace.model_calls.append(model_call)
                
                for tc_data in round_data.get('tool_calls', []):
                    tool_call = ToolCall(**tc_data)
                    round_trace.tool_calls.append(tool_call)
                
                trace_session.bug_fix_rounds.append(round_trace)
        elif data.get('run_rounds'):  
            for round_data in data['run_rounds']:
                round_trace = RunRoundTrace(
                    round_number=round_data.get('round_number', 0),
                    input_list=round_data.get('input_list', []),
                    final_output=round_data.get('final_output', '')
                )
                
                for mc_data in round_data.get('model_calls', []):
                    model_call = ModelCall(**mc_data)
                    round_trace.model_calls.append(model_call)
                
                for tc_data in round_data.get('tool_calls', []):
                    tool_call = ToolCall(**tc_data)
                    round_trace.tool_calls.append(tool_call)
                
                trace_session.bug_fix_rounds.append(round_trace)
        
        if data.get('check_rounds'):
            for ct_data in data['check_rounds']:
                checker_trace = CheckerTrace(**ct_data)
                trace_session.check_rounds.append(checker_trace)
        
        if data.get('patch_selection'):
            ps_data = data['patch_selection']
            patch_selection = PatchSelectionTrace(
                input_patches=ps_data.get('input_patches', []),
                selection_prompt=ps_data.get('selection_prompt', ''),
                selected_patch_index=ps_data.get('selected_patch_index', -1),
                reasoning=ps_data.get('reasoning', ''),
                application_success=ps_data.get('application_success', False)
            )
            
            for mc_data in ps_data.get('model_calls', []):
                model_call = ModelCall(**mc_data)
                patch_selection.model_calls.append(model_call)
            
            for tc_data in ps_data.get('tool_calls', []):
                tool_call = ToolCall(**tc_data)
                patch_selection.tool_calls.append(tool_call)
            
            trace_session.patch_selection = patch_selection
        
        self.trace_session = trace_session
        self.session_id = self.trace_session.session_id
    
    def load_from_json_v2(self, filepath: Union[str, Path]) -> None:
        """
        {
            "trajectory": { BugFixTraceSession的内容 },
            "info": {
                "agent": "siada",
                "submission": "diff内容"
            }
        }
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 'trajectory' not in data or 'info' not in data:
            raise ValueError("Invalid v2 format: missing 'trajectory' or 'info' fields")
        
        trajectory_data = data['trajectory']
        self._load_trajectory_data(trajectory_data)
        
        info_data = data['info']
        self.agent_name = info_data.get('agent', 'siada')
        self.submission_diff = info_data.get('submission', '')
    
    def _load_trajectory_data(self, data: Dict[str, Any]) -> None:
        trace_session = BugFixTraceSession(
            session_id=data.get('session_id', ''),
            original_issue=data.get('original_issue', ''),
            final_result=data.get('final_result', ''),
            success=data.get('success', False),
            error_message=data.get('error_message', '')
        )
        
        if data.get('classify'):
            trace_session.classify = ProjectAnalysisTrace(**data['classify'])
        elif data.get('project_analysis'):
            trace_session.classify = ProjectAnalysisTrace(**data['project_analysis'])
        
        if data.get('issue_optimize'):
            trace_session.issue_optimize = OptimizationTrace(**data['issue_optimize'])
        elif data.get('optimization'):
            trace_session.issue_optimize = OptimizationTrace(**data['optimization'])
        
        if data.get('bug_fix_rounds'):
            for round_data in data['bug_fix_rounds']:
                round_trace = RunRoundTrace(
                    round_number=round_data.get('round_number', 0),
                    input_list=round_data.get('input_list', []),
                    final_output=round_data.get('final_output', '')
                )
                
                for mc_data in round_data.get('model_calls', []):
                    model_call = ModelCall(**mc_data)
                    round_trace.model_calls.append(model_call)
                
                for tc_data in round_data.get('tool_calls', []):
                    tool_call = ToolCall(**tc_data)
                    round_trace.tool_calls.append(tool_call)
                
                trace_session.bug_fix_rounds.append(round_trace)
        elif data.get('run_rounds'):
            for round_data in data['run_rounds']:
                round_trace = RunRoundTrace(
                    round_number=round_data.get('round_number', 0),
                    input_list=round_data.get('input_list', []),
                    final_output=round_data.get('final_output', '')
                )
                
                for mc_data in round_data.get('model_calls', []):
                    model_call = ModelCall(**mc_data)
                    round_trace.model_calls.append(model_call)
                
                for tc_data in round_data.get('tool_calls', []):
                    tool_call = ToolCall(**tc_data)
                    round_trace.tool_calls.append(tool_call)
                
                trace_session.bug_fix_rounds.append(round_trace)
        
        if data.get('check_rounds'):
            for ct_data in data['check_rounds']:
                checker_trace = CheckerTrace(**ct_data)
                trace_session.check_rounds.append(checker_trace)
        
        if data.get('patch_selection'):
            ps_data = data['patch_selection']
            patch_selection = PatchSelectionTrace(
                input_patches=ps_data.get('input_patches', []),
                selection_prompt=ps_data.get('selection_prompt', ''),
                selected_patch_index=ps_data.get('selected_patch_index', -1),
                reasoning=ps_data.get('reasoning', ''),
                application_success=ps_data.get('application_success', False)
            )
            
            for mc_data in ps_data.get('model_calls', []):
                model_call = ModelCall(**mc_data)
                patch_selection.model_calls.append(model_call)
            
            for tc_data in ps_data.get('tool_calls', []):
                tool_call = ToolCall(**tc_data)
                patch_selection.tool_calls.append(tool_call)
            
            trace_session.patch_selection = patch_selection
        
        self.trace_session = trace_session
        self.session_id = self.trace_session.session_id
    
    def formatter_export_data(self, trace_session:BugFixTraceSession)->OutputData:
        output=OutputData(trace_session)

        output.info["agent"]=self.agent_name
        output.info["submission"]=self.submission_diff
        output.info["exit_status"]=self.exit_status

        classify= trace_session.classify
        issue_optimize= trace_session.issue_optimize
        check_rounds= trace_session.check_rounds
        bug_fix_rounds= trace_session.bug_fix_rounds
        overreview="Execution stage: classify"

        output.history.append(
            HistoryItem(execution_stage="classify", content=classify)
        )

        if (issue_optimize!=None):
            overreview+=" -> issue optimize"
            output.history.append(
                HistoryItem(execution_stage="issue optimize", content=issue_optimize)
            )

        check_idx=0
        for id, run in enumerate(bug_fix_rounds):
            overreview+=f" -> bug fix (round {id+1})"
            output.history.append(
                HistoryItem(execution_stage="bug fix", content=run.model_calls[-1])
            )
        
            check_idx+=2
            if (check_idx-2<len(check_rounds)):
                overreview+=f" -> check (round {id+1})" 
                output.history.append(
                    HistoryItem(execution_stage="check", content=check_rounds[check_idx-2])
                )
            if (check_idx-1<len(check_rounds)):
                overreview+=f" -> enhance check (round {id+1})" 
                output.history.append(
                    HistoryItem(execution_stage="enhance check", content=check_rounds[check_idx-1])
                )
        output.trajectory.execution_overview=overreview
        return output

    def load_from_json_v3(self, filepath: Union[str, Path]) -> None:
        """
        {
            "trajectory": { BugFixTraceSession content },
            "info": {
                "agent": "siada",
                "submission": "diff content"
            }
        }
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 'trajectory' not in data or 'info' not in data:
            raise ValueError("Invalid v3 format: missing 'trajectory' or 'info' fields")
        
        trajectory_data = data['trajectory']
        self._load_trajectory_data_old(trajectory_data)
        
        info_data = data['info']
        self.agent_name = info_data.get('agent', 'siada')
        self.submission_diff = info_data.get('submission', '')

    def _load_trajectory_data_old(self, data: Dict[str, Any]) -> None:
        trace_session = BugFixTraceSessionOld(
            session_id=data.get('session_id', ''),
            original_issue=data.get('original_issue', ''),
            final_result=data.get('final_result', ''),
            success=data.get('success', False),
            error_message=data.get('error_message', '')
        )
        
        if data.get('project_domain_classification'):
            trace_session.project_domain_classification = ProjectAnalysisTrace(**data['project_domain_classification'])
        elif data.get('project_analysis'):
            trace_session.project_domain_classification = ProjectAnalysisTrace(**data['project_analysis'])
        
        if data.get('issue_description_optimization'):
            trace_session.issue_description_optimization = OptimizationTrace(**data['issue_description_optimization'])
        elif data.get('optimization'):
            trace_session.issue_description_optimization = OptimizationTrace(**data['optimization'])
        
        if data.get('bug_fix_run_rounds'):
            for round_data in data['bug_fix_run_rounds']:
                round_trace = RunRoundTrace(
                    round_number=round_data.get('round_number', 0),
                    input_list=round_data.get('input_list', []),
                    final_output=round_data.get('final_output', '')
                )
                
                for mc_data in round_data.get('model_calls', []):
                    model_call = ModelCall(**mc_data)
                    round_trace.model_calls.append(model_call)
                
                for tc_data in round_data.get('tool_calls', []):
                    tool_call = ToolCall(**tc_data)
                    round_trace.tool_calls.append(tool_call)
                
                trace_session.bug_fix_run_rounds.append(round_trace)
        elif data.get('run_rounds'):
            for round_data in data['run_rounds']:
                round_trace = RunRoundTrace(
                    round_number=round_data.get('round_number', 0),
                    input_list=round_data.get('input_list', []),
                    final_output=round_data.get('final_output', '')
                )
                
                for mc_data in round_data.get('model_calls', []):
                    model_call = ModelCall(**mc_data)
                    round_trace.model_calls.append(model_call)
                
                for tc_data in round_data.get('tool_calls', []):
                    tool_call = ToolCall(**tc_data)
                    round_trace.tool_calls.append(tool_call)
                
                trace_session.bug_fix_run_rounds.append(round_trace)
        
        if data.get('checker_traces'):
            for ct_data in data['checker_traces']:
                checker_trace = CheckerTrace(**ct_data)
                trace_session.checker_traces.append(checker_trace)
        
        if data.get('patch_selection'):
            ps_data = data['patch_selection']
            patch_selection = PatchSelectionTrace(
                input_patches=ps_data.get('input_patches', []),
                selection_prompt=ps_data.get('selection_prompt', ''),
                selected_patch_index=ps_data.get('selected_patch_index', -1),
                reasoning=ps_data.get('reasoning', ''),
                application_success=ps_data.get('application_success', False)
            )
            
            for mc_data in ps_data.get('model_calls', []):
                model_call = ModelCall(**mc_data)
                patch_selection.model_calls.append(model_call)
            
            for tc_data in ps_data.get('tool_calls', []):
                tool_call = ToolCall(**tc_data)
                patch_selection.tool_calls.append(tool_call)
            
            trace_session.patch_selection = patch_selection
        
        trace=BugFixTraceSession(
            trace_session.session_id,trace_session.original_issue,
            trace_session.execution_overview,trace_session.project_domain_classification,
            trace_session.issue_description_optimization,trace_session.bug_fix_run_rounds,
            trace_session.checker_traces,trace_session.patch_selection,trace_session.final_result,
            trace_session.success,trace_session.error_message
        )

        self.trace_session = trace
        self.session_id = self.trace_session.session_id
    

    @classmethod
    def create_analyzer(cls, traces_dir: str = "bug_fix_traces") -> "BugFixTraceAnalyzer":
        return BugFixTraceAnalyzer(traces_dir)


class BugFixTraceAnalyzer:
    
    def __init__(self, traces_dir: str):
        self.traces_dir = Path(traces_dir)
    
    def load_all_traces(self) -> List[BugFixTraceSession]:
        traces = []
        for json_file in self.traces_dir.glob("*.json"):
            try:
                collector = BugFixTraceCollector()
                collector.load_from_json(json_file)
                traces.append(collector.trace_session)
            except Exception as e:
                print(f"Failed to load {json_file}: {e}")
        return traces
    
    def analyze_success_rate(self) -> Dict[str, Any]:
        traces = self.load_all_traces()
        if not traces:
            return {"total": 0, "success": 0, "success_rate": 0.0}
        
        total = len(traces)
        success = sum(1 for trace in traces if trace.success)
        
        return {
            "total": total,
            "success": success,
            "failed": total - success,
            "success_rate": success / total if total > 0 else 0.0
        }
    
    def analyze_performance_metrics(self) -> Dict[str, Any]:
        traces = self.load_all_traces()
        if not traces:
            return {}
        
        round_counts = [len(trace.bug_fix_rounds) for trace in traces]
        model_call_counts = [
            sum(len(round_trace.model_calls) for round_trace in trace.bug_fix_rounds)
            for trace in traces
        ]
        tool_call_counts = [
            sum(len(round_trace.tool_calls) for round_trace in trace.bug_fix_rounds)
            for trace in traces
        ]
        
        return {
            "avg_rounds": sum(round_counts) / len(round_counts) if round_counts else 0,
            "avg_model_calls": sum(model_call_counts) / len(model_call_counts) if model_call_counts else 0,
            "avg_tool_calls": sum(tool_call_counts) / len(tool_call_counts) if tool_call_counts else 0,
            "max_rounds": max(round_counts) if round_counts else 0,
            "min_rounds": min(round_counts) if round_counts else 0
        }
    
    def generate_report(self) -> Dict[str, Any]:
        success_stats = self.analyze_success_rate()
        performance_stats = self.analyze_performance_metrics()
        
        return {
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "success_analysis": success_stats,
            "performance_analysis": performance_stats,
            "traces_analyzed": success_stats["total"]
        }

def create_bug_fix_trace_collector(
    output_dir: Optional[str] = None, 
    console_output: bool = True,
    session_id: Optional[str] = None
) -> BugFixTraceCollector:
    """Create a BugFix trace collector with default settings"""
    # If no output directory is specified, use the default trace directory
    if output_dir is None:
        import os
        from datetime import datetime
        
        # Create trace directory (unified across all platforms)  
        from pathlib import Path
        trace_dir = Path.home() / ".siada-cli" / "traces" / "bug_fix"
        trace_dir.mkdir(parents=True, exist_ok=True)
        
        output_dir = str(trace_dir)
    
    return BugFixTraceCollector(
        session_id=session_id,
        output_dir=output_dir,
        show_model_calls=True,
        show_tool_calls=True,
        show_handoffs=True,
        show_trace_lifecycle=True,
        show_timestamps=True,
        show_system_messages=False,
        use_colors=True,
        console_output=console_output,
        output_file=None,  # BugFixTraceCollector使用JSON文件而不是log文件
        indent_level=0
    )


def create_simple_bug_fix_trace_collector(console_output: bool = True) -> BugFixTraceCollector:
    """Create a simple BugFix trace collector"""
    return BugFixTraceCollector(
        console_output=console_output,
        show_model_calls=True,
        show_tool_calls=False,
        show_handoffs=False,
        show_trace_lifecycle=False,
        use_colors=False
    )


def create_file_only_bug_fix_trace_collector(output_dir: Optional[str] = None) -> BugFixTraceCollector:
    """Create a BugFix trace collector that only writes to file (no console output)"""
    return create_bug_fix_trace_collector(output_dir=output_dir, console_output=False)


def create_custom_bug_fix_trace_collector(
    session_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    console_output: bool = True,
    show_model_calls: bool = True,
    show_tool_calls: bool = True,
    show_handoffs: bool = True,
    show_trace_lifecycle: bool = True
) -> BugFixTraceCollector:
    """Create a customized BugFix trace collector"""
    if output_dir is None:
        from pathlib import Path
        trace_dir = Path.home() / ".siada-cli" / "traces" / "bug_fix"
        trace_dir.mkdir(parents=True, exist_ok=True)
        output_dir = str(trace_dir)
    
    return BugFixTraceCollector(
        session_id=session_id,
        output_dir=output_dir,
        show_model_calls=show_model_calls,
        show_tool_calls=show_tool_calls,
        show_handoffs=show_handoffs,
        show_trace_lifecycle=show_trace_lifecycle,
        show_timestamps=True,
        use_colors=True,
        console_output=console_output
    )
