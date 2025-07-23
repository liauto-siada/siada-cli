"""
Run Turn Module

Manages individual interaction turns between user and AI, including command processing
and model conversations. Encapsulates the logic for a single interaction cycle.
"""

from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod
from enum import Enum

from agents import RawResponsesStreamEvent, RunResultStreaming, StreamEvent

# Import existing InteractionConfig
from .interaction_controller import InteractionConfig


class TurnType(Enum):
    """Types of interaction turns"""
    COMMAND = "command"          # Slash commands (/help, /edit, etc.)
    CONVERSATION = "conversation" # Regular AI conversation


@dataclass
class TurnInput:
    """Input data for a turn"""
    use_input: str                 # Raw user input
    turn_type: TurnType           # Type of this turn


@dataclass
class TurnOutput:
    """Output data from a turn"""
    content: str                # Response content
    metadata: Dict[str, Any]    # Response metadata
    next_action: Optional[str]  # Suggested next action


class RunTurn(ABC):
    """Abstract base class for interaction turns"""
    
    def __init__(self, config: InteractionConfig, session: Any):
        """Initialize turn with configuration and session
        
        Args:
            config: InteractionConfig with execution parameters
            session: Current session instance
        """
        self.config = config
        self.session = session
        
        # Data tracking
        self.input_data: Optional[TurnInput] = None
        self.output_data: Optional[TurnOutput] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.error: Optional[Exception] = None
    
    @abstractmethod
    def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute the turn with given input
        
        Args:
            turn_input: Input data for this turn
            
        Returns:
            TurnOutput: Result of turn execution
        """
        pass
    
    def can_handle(self, user_input: str) -> bool:
        """Check if this turn type can handle the given input
        
        Args:
            user_input: Raw user input string
            
        Returns:
            bool: True if this turn can handle the input
        """
        return True
    
    def prepare_input(self, raw_input: str) -> TurnInput:
        """Prepare turn input from raw user input
        
        Args:
            raw_input: Raw user input string
            
        Returns:
            TurnInput: Prepared input for turn execution
        """
        return TurnInput(
            use_input=raw_input,
            turn_type=self.get_turn_type()
        )
    
    def get_turn_type(self) -> TurnType:
        """Get the type of this turn
        
        Returns:
            TurnType: Type of this turn
        """
        return TurnType.CONVERSATION
    
    def validate_input(self, turn_input: TurnInput) -> bool:
        """Validate turn input
        
        Args:
            turn_input: Input to validate
            
        Returns:
            bool: True if input is valid
        """
        return bool(turn_input.use_input and turn_input.use_input.strip())
    
    def handle_error(self, error: Exception) -> TurnOutput:
        """Handle execution error
        
        Args:
            error: Exception that occurred
            
        Returns:
            TurnOutput: Error response
        """
        self.error = error
        
        return TurnOutput(
            content=f"Error: {str(error)}",
            metadata={"error_type": type(error).__name__},
            artifacts=[]
        )
    
    def _get_timestamp(self) -> float:
        """Get current timestamp"""
        import time
        return time.time()


class ConversationTurn(RunTurn):
    """Handles regular AI conversation turns"""

    def get_turn_type(self) -> TurnType:
        return TurnType.CONVERSATION

    def can_handle(self, user_input: str) -> bool:
        """Handle non-command input"""
        return not self.config.slash_commands.is_command(user_input)

    async def process_stream_event(self, result: RunResultStreaming) -> None:
        """Process stream events and handle real-time output"""
        from openai.types.responses import (
            ResponseTextDeltaEvent,
            ResponseReasoningSummaryTextDeltaEvent,
            ResponseFunctionCallArgumentsDeltaEvent,
            ResponseContentPartAddedEvent,
            ResponseOutputItemAddedEvent,
            ResponseCompletedEvent,
            ResponseCreatedEvent
        )
        
        async for event in result.stream_events():
            if not isinstance(event, RawResponsesStreamEvent):
                continue
                
            # Handle the raw response stream event
            stream_event = event.event
            
            # Handle different types of stream events
            if isinstance(stream_event, ResponseCreatedEvent):
                # Response started
                self.config.io.print_info("🤖 AI is thinking...")
            
            elif isinstance(stream_event, ResponseTextDeltaEvent):
                # Stream text content in real-time
                if hasattr(self.config.io, 'print_messages'):
                    self.config.io.print_messages(stream_event.delta, color_name='output', end='')
                else:
                    print(stream_event.delta, end='', flush=True)
            
            elif isinstance(stream_event, ResponseReasoningSummaryTextDeltaEvent):
                # Stream reasoning/thinking content
                if hasattr(self.config.io, 'print_messages'):
                    self.config.io.print_messages(stream_event.delta, color_name='tool_call_color', end='')
                else:
                    print(f"💭 {stream_event.delta}", end='', flush=True)
            
            elif isinstance(stream_event, ResponseFunctionCallArgumentsDeltaEvent):
                # Stream function call arguments
                if hasattr(self.config.io, 'print_messages'):
                    self.config.io.print_messages(stream_event.delta, color_name='tool_result_color', end='')
                else:
                    print(f"🔧 {stream_event.delta}", end='', flush=True)
            
            elif isinstance(stream_event, ResponseContentPartAddedEvent):
                # New content part started
                if stream_event.part.type == "output_text":
                    print("\n", end='')  # New line for new content part
            
            elif isinstance(stream_event, ResponseOutputItemAddedEvent):
                # New output item started
                if hasattr(stream_event.item, 'type'):
                    if stream_event.item.type == "message":
                        print("\n🤖 ", end='')
                    elif stream_event.item.type == "function_call":
                        print(f"\n🔧 Function call: {getattr(stream_event.item, 'name', 'unknown')}")
                    elif stream_event.item.type == "reasoning":
                        print("\n💭 Reasoning: ", end='')
            
            elif isinstance(stream_event, ResponseCompletedEvent):
                # Response completed
                print("\n")  # Final newline
                self.config.io.print_info("✅ Response completed")

    def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute AI conversation turn
        
        Args:
            turn_input: User input for conversation
            
        Returns:
            TurnOutput: AI response
        """
        self.input_data = turn_input
        self.start_time = self._get_timestamp()

        try:
            # Import here to avoid circular imports
            from siada.services.siada_runner import SiadaRunner

            # Run agent for conversation
            result: RunResultStreaming = SiadaRunner.run_agent(
                agent_name=self.config.agent_name,
                user_input=turn_input.use_input,
                workspace=self.config.workspace,
                session=self.session,
                stream=True,
            )

            result.stream_events()

            self.end_time = self._get_timestamp()

            output = TurnOutput(
                content=result.final_output,
                metadata={
                    "agent_used": self.config.agent_name,
                    "execution_time": self.end_time - self.start_time
                },
                next_action=None
            )

            self.output_data = output
            return output

        except Exception as e:
            self.end_time = self._get_timestamp()
            return self.handle_error(e)


class CommandTurn(RunTurn):
    """Handles slash command turns"""
    
    def get_turn_type(self) -> TurnType:
        return TurnType.COMMAND
    
    def can_handle(self, user_input: str) -> bool:
        """Handle slash commands"""
        return self.config.slash_commands.is_command(user_input)
    
    def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute slash command
        
        Args:
            turn_input: Command input
            
        Returns:
            TurnOutput: Command result
        """
        self.input_data = turn_input
        self.start_time = self._get_timestamp()
        
        try:
            result = self.config.slash_commands.run(turn_input.use_input)
            self.end_time = self._get_timestamp()
            
            output = TurnOutput(
                content=result,
                metadata={
                    "execution_time": self.end_time - self.start_time
                },
                next_action=None
            )
            
            self.output_data = output
            return output
              
        except Exception as e:
            self.end_time = self._get_timestamp()
            return self.handle_error(e)


class TurnFactory:
    """Factory for creating appropriate turn instances"""
    
    def __init__(self, config: InteractionConfig, session: Any):
        """Initialize factory with configuration and session
        
        Args:
            config: InteractionConfig with execution parameters
            session: Current session instance
        """
        self.config = config
        self.session = session
        
        self.turn_handlers = [
            CommandTurn(config, session),
            ConversationTurn(config, session),
        ]
    
    def create_turn(self, user_input: str) -> RunTurn:
        """Create appropriate turn for user input
        
        Args:
            user_input: Raw user input
            
        Returns:
            RunTurn: Appropriate turn handler
        """
        for handler in self.turn_handlers:
            if handler.can_handle(user_input):
                return handler
        
        # Default to conversation turn
        return ConversationTurn(self.config, self.session)


class TurnManager:
    """Manages turn execution and history"""
    
    def __init__(self, config: InteractionConfig, session: Any):
        """Initialize turn manager
        
        Args:
            config: InteractionConfig with execution parameters
            session: Current session instance
        """
        self.config = config
        self.session = session
        
        self.factory = TurnFactory(config, session)
        self.turn_history: List[RunTurn] = []
        self.current_turn: Optional[RunTurn] = None
    
    def execute_turn(self, user_input: str) -> TurnOutput:
        """Execute a single turn
        
        Args:
            user_input: Raw user input
            
        Returns:
            TurnOutput: Result of turn execution
        """
        # Create appropriate turn
        turn = self.factory.create_turn(user_input)
        self.current_turn = turn
        
        # Prepare input
        turn_input = turn.prepare_input(user_input)
        
        # Validate input
        if not turn.validate_input(turn_input):
            return TurnOutput(
                content="Invalid input provided",
                metadata={},
                artifacts=[]
            )
        
        # Execute turn
        try:
            output = turn.execute(turn_input)
            
            # Add to history
            self.turn_history.append(turn)
            
            # Output result
            if output.content:
                self.config.io.print_info(output.content)
            
            return output
            
        except Exception as e:
            return turn.handle_error(e)
    
    def get_turn_history(self) -> List[RunTurn]:
        """Get turn execution history
        
        Returns:
            List[RunTurn]: History of executed turns
        """
        return self.turn_history.copy()
    
    def clear_history(self) -> None:
        """Clear turn history"""
        self.turn_history.clear()
    
    def get_last_turn(self) -> Optional[RunTurn]:
        """Get the last executed turn
        
        Returns:
            Optional[RunTurn]: Last turn or None if no history
        """
        return self.turn_history[-1] if self.turn_history else None 
