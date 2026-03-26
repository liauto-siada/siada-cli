"""
Token Usage Reporter Processor

Reports API token usage to telemetry system after each LLM call.
"""

import logging
from typing import Optional, Dict, Any
from agents import Agent, ModelResponse, AgentHooks, TContext, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.telemetry import telemetry

logger = logging.getLogger(__name__)


class TokenUsageReporterProcessor(AgentHooks):
    """
    Processor for reporting API token usage to telemetry system.
    
    This processor:
    - Captures token usage after each LLM call (on_llm_end)
    - Calculates cache tokens and total cost
    - Reports to telemetry only for internal builds with 'li' provider
    """

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        """
        Called immediately after the LLM call returns.
        Captures and reports token usage.
        """
        try:
            # 1. Get session and config
            siada_context = context.context
            session = siada_context.session
            if not session:
                return
            
            siada_config = session.siada_config
            if not siada_config:
                return
            
            # 2. Check if should report (internal build + li provider)
            if not self._should_report(siada_config):
                return
            
            # 3. Get usage from response
            usage = response.usage
            if not usage:
                return
            
            # 4. Extract and calculate token details
            token_data = self._extract_token_data(usage)
            
            # 5. Get model name and convert for li provider
            model_name = self._get_model_name(siada_config)
            if not model_name:
                return
            
            # 6. Calculate total cost
            total_cost = self._calculate_cost(model_name, token_data)
            
            # 7. Report to telemetry
            telemetry.captureApiTokenUsage(
                task_id=session.session_id,
                input_tokens=token_data['input_tokens'],
                output_tokens=token_data['output_tokens'],
                cache_write_tokens=token_data['cache_write_tokens'],
                cache_read_tokens=token_data['cache_read_tokens'],
                model=model_name,
                total_cost=total_cost,
                ide_type="cli"
            )
            
        except Exception as e:
            # Telemetry errors should not affect main functionality
            logger.debug(f"Failed to report token usage: {e}")

    def _should_report(self, siada_config) -> bool:
        """
        Determine whether token usage should be reported.

        Conditions:
        1. telemetry.config.conversation_url is non-empty (internal build)
        2. provider is 'li'

        Args:
            siada_config: Running configuration

        Returns:
            bool: True if should report, False otherwise
        """
        # Check if telemetry is enabled (non-empty conversation_url indicates internal build)
        if not telemetry.config.conversation_url:
            return False
        
        # Check if provider is 'li'
        if hasattr(siada_config, 'llm_config') and hasattr(siada_config.llm_config, 'provider'):
            return siada_config.llm_config.provider == 'li'
        
        return False

    def _extract_token_data(self, usage) -> Dict[str, int]:
        """
        Extract token data from the usage object and calculate cache tokens.

        Args:
            usage: Usage object from ModelResponse

        Returns:
            Dict containing input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
        """
        # Get basic token data
        input_tokens = usage.input_tokens if hasattr(usage, 'input_tokens') and usage.input_tokens else 0
        output_tokens = usage.output_tokens if hasattr(usage, 'output_tokens') and usage.output_tokens else 0
        
        # Extract cache_read_tokens
        cache_read_tokens = 0
        if hasattr(usage, 'input_tokens_details') and usage.input_tokens_details:
            if hasattr(usage.input_tokens_details, 'cached_tokens') and usage.input_tokens_details.cached_tokens:
                cache_read_tokens = usage.input_tokens_details.cached_tokens
        
        # Calculate cache_write_tokens (derived from total_tokens)
        cache_write_tokens = 0
        if hasattr(usage, 'total_tokens') and usage.total_tokens:
            calculated_total = input_tokens + output_tokens + cache_read_tokens
            if usage.total_tokens > calculated_total:
                cache_write_tokens = usage.total_tokens - calculated_total
        
        return {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cache_read_tokens': cache_read_tokens,
            'cache_write_tokens': cache_write_tokens
        }

    def _get_model_name(self, siada_config) -> Optional[str]:
        """
        Retrieve the model name and convert it to the li provider format.

        Args:
            siada_config: Running configuration

        Returns:
            Converted model name, or None if not available
        """
        # Get original model name
        if not hasattr(siada_config, 'llm_config') or not hasattr(siada_config.llm_config, 'model_name'):
            return None
        
        model_name = siada_config.llm_config.model_name
        if not model_name:
            return None
        
        # Convert to li provider format
        try:
            from siada.provider.li.coverter import covert_to_li_model_name
            return covert_to_li_model_name(model_name)
        except Exception as e:
            logger.debug(f"Failed to convert model name: {e}")
            return model_name

    def _calculate_cost(self, model_name: str, token_data: Dict[str, int]) -> float:
        """
        Calculate the total cost of token usage.

        Args:
            model_name: Model name
            token_data: Token data dict

        Returns:
            Total cost in CNY
        """
        try:
            from siada.models.model_pricing import calculate_token_cost
            return calculate_token_cost(
                model_name=model_name,
                input_tokens=token_data['input_tokens'],
                output_tokens=token_data['output_tokens'],
                cache_write_tokens=token_data['cache_write_tokens'],
                cache_read_tokens=token_data['cache_read_tokens']
            )
        except Exception as e:
            logger.debug(f"Failed to calculate cost: {e}")
            return 0.0

    async def on_llm_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        system_prompt: Optional[str],
        input_items: list,
    ) -> None:
        """Called just before invoking the LLM."""
        pass

    async def on_agent_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        """Called when an agent starts execution."""
        pass

    async def on_agent_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        """Called when an agent completes execution."""
        pass

    async def on_tool_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Any,
    ) -> None:
        """Called before a tool is executed."""
        pass

    async def on_tool_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Any,
        result: str,
    ) -> None:
        """Called after a tool completes execution."""
        pass
