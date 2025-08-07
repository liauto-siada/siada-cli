"""
Context Trimming Model Wrapper

A wrapper for any Model implementation that allows custom input processing/trimming
before passing to the underlying model. This wrapper is fully backward compatible
and transparent to the agents framework.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Callable

from agents import Model, TResponseInputItem, ModelSettings, AgentOutputSchemaBase, Handoff, ModelTracing, \
    ModelResponse, ModelProvider
from agents.items import TResponseStreamEvent
from openai.types.responses.response_prompt_param import ResponsePromptParam

from siada.models.agent import Tool


class ModelWrapper(Model):
    """
    A wrapper around any Model implementation that allows custom input processing.
    
    This wrapper intercepts calls to get_response() and stream_response() to apply
    custom input filtering/trimming logic before passing to the underlying model.
    
    Example:
        def my_input_processor(input_items):
            # Your custom logic here
            return input_items[-10:]  # Keep only last 10 items
        
        original_model = OpenAIChatCompletionsModel("gpt-4")
        wrapped_model = ContextTrimmingModel(original_model, my_input_processor)
        
        # Use in RunConfig
        run_config = RunConfig(model=wrapped_model)
    """
    
    def __init__(
        self,
        wrapped_model: Model,
        input_processor: Callable[[list[TResponseInputItem]], list[TResponseInputItem]] | None = None,
    ):
        """
        Initialize the context trimming model wrapper.
        
        Args:
            wrapped_model: The underlying Model implementation to wrap
            input_processor: Optional function to process/trim input items.
                           If None, input will be passed through unchanged.
                           Function signature: (input_items: list[TResponseInputItem]) -> list[TResponseInputItem]
        """
        self.wrapped_model = wrapped_model
        self.input_processor = input_processor
        
        # Store metadata about the wrapped model for debugging
        self._wrapped_model_type = type(wrapped_model).__name__
        self._wrapped_model_str = str(wrapped_model)
    
    def _process_input(
        self, 
        input: str | list[TResponseInputItem]
    ) -> str | list[TResponseInputItem]:
        """
        Process the input using the configured input_processor.
        
        Args:
            input: The original input (string or list of items)
            
        Returns:
            Processed input (same type as input)
        """
        # If no processor is configured, pass through unchanged
        if self.input_processor is None:
            return input
        
        # Only process list inputs, pass string inputs through unchanged
        if isinstance(input, list):
            try:
                processed = self.input_processor(input)
                # Ensure the processor returns a list
                if not isinstance(processed, list):
                    raise ValueError(f"Input processor must return a list, got {type(processed)}")
                return processed
            except Exception as e:
                # Log the error but don't break the flow - fall back to original input
                print(f"Warning: Input processor failed with error: {e}. Using original input.")
                return input
        
        return input
    
    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        """
        Get a response from the wrapped model with input processing.
        
        This method processes the input using the configured input_processor
        before passing it to the underlying model.
        """
        # Process the input
        processed_input = self._process_input(input)
        
        # Call the wrapped model with processed input
        return await self.wrapped_model.get_response(
            system_instructions=system_instructions,
            input=processed_input,
            model_settings=model_settings,
            tools=tools,
            output_schema=output_schema,
            handoffs=handoffs,
            tracing=tracing,
            previous_response_id=previous_response_id,
            prompt=prompt,
        )
    
    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        """
        Stream a response from the wrapped model with input processing.
        
        This method processes the input using the configured input_processor
        before passing it to the underlying model.
        """
        # Process the input
        processed_input = self._process_input(input)
        
        # Call the wrapped model with processed input
        return self.wrapped_model.stream_response(
            system_instructions=system_instructions,
            input=processed_input,
            model_settings=model_settings,
            tools=tools,
            output_schema=output_schema,
            handoffs=handoffs,
            tracing=tracing,
            previous_response_id=previous_response_id,
            prompt=prompt,
        )
    
    def __str__(self) -> str:
        """String representation for debugging."""
        return f"ContextTrimmingModel(wrapped={self._wrapped_model_type})"
    
    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        processor_info = "with processor" if self.input_processor else "no processor"
        return f"ContextTrimmingModel(wrapped={self._wrapped_model_str}, {processor_info})"


class ModelProviderWrapper(ModelProvider):
    """
    A ModelProvider wrapper that automatically applies context trimming to all models.

    This provider wraps any underlying ModelProvider and automatically applies
    the same input processing logic to all models it provides.

    Example:
        def my_input_processor(input_items):
            return input_items[-10:]  # Keep only last 10 items

        base_provider = MultiProvider()
        trimming_provider = ContextTrimmingModelProvider(base_provider, my_input_processor)

        # Use in RunConfig - all models will be automatically wrapped
        run_config = RunConfig(model_provider=trimming_provider)
    """

    def __init__(
            self,
            base_provider: ModelProvider,
            input_processor: Callable[[list[TResponseInputItem]], list[TResponseInputItem]] | None = None,
    ):
        """
        Initialize the context trimming model provider.

        Args:
            base_provider: The underlying ModelProvider to wrap
            input_processor: Optional function to process/trim input items for all models.
                           If None, models will be returned without wrapping.
        """
        self.base_provider = base_provider
        self.input_processor = input_processor

    def get_model(self, model_name: str | None) -> Model:
        """
        Get a model from the base provider and wrap it with context trimming.

        Args:
            model_name: The name of the model to get

        Returns:
            A ContextTrimmingModel wrapping the requested model
        """
        # Get the base model
        base_model = self.base_provider.get_model(model_name)

        # If no processor is configured, return the base model unchanged
        if self.input_processor is None:
            return base_model

        # Wrap with context trimming
        return ModelWrapper(base_model, self.input_processor)

    def __str__(self) -> str:
        """String representation for debugging."""
        return f"ContextTrimmingModelProvider(base={type(self.base_provider).__name__})"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        processor_info = "with processor" if self.input_processor else "no processor"
        return f"ContextTrimmingModelProvider(base={self.base_provider}, {processor_info})"

