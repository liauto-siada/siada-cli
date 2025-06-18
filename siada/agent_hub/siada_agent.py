from abc import ABC, abstractmethod
from typing import Generic

from agents import Agent, RunResult, TContext


class SiadaAgent(Agent[Generic[TContext]], ABC):
    
    @abstractmethod
    async def get_context(self) -> TContext:
        """
        Get the context object for this agent.
        
        Returns:
            TContext: The context object containing relevant information for the agent's execution.
        """
        pass
    
    @abstractmethod
    async def run(self, user_input: str, context: TContext) -> RunResult:
        """
        Execute the agent with the given user input and context.
        
        Args:
            user_input (str): The input provided by the user.
            context (TContext): The context object containing relevant information for execution.
            
        Returns:
            RunResult: The result of the agent's execution.
        """
        pass
