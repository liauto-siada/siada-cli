"""
Smart Memory Search Tool

Provides an intelligent memory search tool that uses a sub-agent to search,
analyze, and summarize memory information. This reduces context window usage
for the main agent while providing more relevant and concise results.
"""

import logging
from pathlib import Path
from typing import Literal, Optional
from agents import Agent, Runner, RunContextWrapper, function_tool
from siada.foundation.code_agent_context import CodeAgentContext
from siada.services.memory import DEFAULT_CHUNK_SIZE
from siada.tools.memory.memory_tool import search_memory_impl
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.services.sub_agent_run_config import build_sub_agent_run_config
from datetime import datetime

logger = logging.getLogger(__name__)


# Global memory search agent instance
_GLOBAL_MEMORY_SEARCH_AGENT: Optional[Agent] = None


# ---- System Prompt for Memory Search Agent --------------------------------

_MEMORY_DIR = str(Path.home() / ".siada-cli" / "workspace" / "memory")

MEMORY_SEARCH_AGENT_PROMPT = f"""You are a specialized memory search assistant. Your job is to find and summarize relevant information from the user's memory files.

## Memory Directory Structure

All memory files live under `{_MEMORY_DIR}`:

```
{_MEMORY_DIR}
├── personal_style.md       # personal style, work habits, communication preferences
├── experience/             # long-term engineering rules, design patterns, architecture facts
│   └── <topic>.md
├── events/                 # structured summaries of recent work sessions (newest = most relevant)
│   └── YYYY-MM-DD-HH-MM-<topic>.md
└── session/                # raw session conversation history (indexed in FTS DB)
    └── YYYY-MM-DD-HH-MM-<slug>.md
```

## Search Strategy (strict priority)

**Step 1 — experience, events, personal_style (search first, always):**
- Use `regex_search_files` to search query keywords across `{_MEMORY_DIR}/experience/` and `{_MEMORY_DIR}/events/` directories
- Read `{_MEMORY_DIR}/personal_style.md` with `edit_file view`
- Read relevant files found above with `edit_file view`

**Step 2 — session (fallback only, if Step 1 yields nothing relevant):**
- Use `search_memory` (FTS DB) to locate matching session files
- Read matching session files with `edit_file view`

## Output Guidelines

- **Brief mode**: 1-2 paragraphs with key points only
- **Medium mode**: 3-5 paragraphs with organized details
- **Detailed mode**: Comprehensive summary with all relevant context

Always cite sources (file paths). Don't make up information — only report what you found. If nothing relevant is found, say so clearly.
"""


# ---- Memory Search Agent Implementation --------------------------------

def get_memory_search_agent(context: CodeAgentContext) -> Agent:
    """
    Get or create the global memory search agent instance.
    
    This agent is designed to be lightweight and efficient. It's created once
    and reused across all memory search requests to avoid overhead.
    
    Args:
        context: Code agent context containing model configuration
        
    Returns:
        Agent: Configured memory search agent
    """
    global _GLOBAL_MEMORY_SEARCH_AGENT
    
    # Return existing agent if already created
    if _GLOBAL_MEMORY_SEARCH_AGENT is not None:
        return _GLOBAL_MEMORY_SEARCH_AGENT
    
    # search_memory wraps the DB search impl directly (no context needed)
    @function_tool
    def search_memory(
        query: str,
        max_results: int = 5,
        min_score: float = 0.0
    ) -> str:
        """Search session memory files using FTS full-text search.
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return
            min_score: Minimum relevance score threshold
            
        Returns:
            Formatted search results with file paths and snippets
        """
        return search_memory_impl(query, max_results, min_score)

    # Get model configuration from context (same as build_context does)
    if not context or not context.session:
        raise ValueError("[MemorySearchAgent] Context or session is required")

    llm_config = context.session.siada_config.llm_config
    model = llm_config.model_name

    # Create the agent (model will be set in RunConfig, not here)
    _GLOBAL_MEMORY_SEARCH_AGENT = Agent(
        name="MemorySearchAgent",
        instructions=MEMORY_SEARCH_AGENT_PROMPT,
        tools=[search_memory, edit, regex_search_files],
    )

    logger.info(f"[MemorySearchAgent] Created with model from config: {model}")
    
    return _GLOBAL_MEMORY_SEARCH_AGENT


# ---- Smart Search Memory Tool --------------------------------

SMART_SEARCH_MEMORY_DOCS = """Intelligently search and summarize information from memory files.

This tool uses an AI agent to search through all memory types — personal style,
long-term experience, structured session events (high priority), and raw session
history (fallback) — then analyze and return a concise, relevant summary.

Use this tool when you need to:
- Find information from past conversations
- Understand context from previous work
- Recall decisions or preferences discussed earlier
- Get a summary of related topics from history

Args:
    query (str): The question or topic to search for
    max_tokens (int, optional): Maximum tokens in the response. Defaults to 2048.
    detail_level (str, optional): Level of detail - "brief", "medium", or "detailed". 
                                  Defaults to "medium".

Returns:
    str: A structured summary with relevant information and source citations

Examples:
    smart_search_memory("What API design decisions did we make?")
    smart_search_memory("上次讨论的数据库方案", detail_level="detailed")
    smart_search_memory("recent bug fixes", max_tokens=1000, detail_level="brief")
"""



async def _smart_search_memory_impl(
    context: CodeAgentContext,
    query: str,
    max_tokens: int = DEFAULT_CHUNK_SIZE,
    detail_level: Literal["brief", "medium", "detailed"] = "medium"
) -> str:
    """
    Internal implementation of smart memory search.
    
    This function gets the global memory search agent, builds a RunConfig
    (similar to build_context), and runs the agent with the user's query.
    
    Args:
        context: Code agent context for accessing configuration
        query: The search query
        max_tokens: Maximum tokens in the response
        detail_level: Level of detail for the response
        
    Returns:
        Structured summary of relevant memory information
    """
    try:
        # Validate input
        if not query or not query.strip():
            return "Error: Search query cannot be empty"
        
        if max_tokens <= 0:
            return "Error: max_tokens must be greater than 0"
        
        if detail_level not in ["brief", "medium", "detailed"]:
            return f"Error: detail_level must be 'brief', 'medium', or 'detailed', got '{detail_level}'"
        
        # Get the global memory search agent
        agent = get_memory_search_agent(context)

        # Build RunConfig with model configuration
        run_config = build_sub_agent_run_config(context)

        # Construct the user input with instructions
        user_input = f"""Please search memory and provide a {detail_level} answer to this question:

{query}

Remember to:
- Search experience/ and events/ first (use regex_search_files with both Chinese and English keywords).
- Always read personal_style.md.
- Fall back to search_memory (session DB) only if the above yield nothing relevant.
- Cite your sources (file paths).
- Keep the response under {max_tokens} tokens.

Current time :
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

        # Build agent context rooted at the memory directory so edit_file resolves paths correctly
        memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        agent_context = CodeAgentContext(root_dir=str(memory_dir))

        # Run the agent with RunConfig (non-streaming)
        logger.info(f"[SmartMemorySearch] Running memory search for query: {query[:100]}...")

        result = await Runner.run(
            agent,
            input=user_input,
            run_config=run_config,
            context=agent_context,
            max_turns=10,
        )
        
        # Extract the final output
        final_output = result.final_output
        
        if not final_output:
            return "No relevant information found in memory."
        
        # Add metadata header
        header = f"# Memory Search Results\n\n**Query:** {query}\n**Detail Level:** {detail_level}\n\n---\n\n"
        
        return header + final_output
        
    except Exception as e:
        error_msg = f"Error in smart memory search: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@function_tool(
    name_override="smart_search_memory",
    description_override=SMART_SEARCH_MEMORY_DOCS
)
async def smart_search_memory(
    context: RunContextWrapper[CodeAgentContext],
    query: str,
    max_tokens: int = DEFAULT_CHUNK_SIZE,
    detail_level: Literal["brief", "medium", "detailed"] = "medium"
) -> str:
    """
    Smart memory search tool that uses a sub-agent to search and summarize memory.
    
    This is the public tool function exposed to agents.
    
    Args:
        context: Run context wrapper (required by function_tool)
        query: The search query
        max_tokens: Maximum tokens in the response
        detail_level: Level of detail for the response
        
    Returns:
        Structured summary of relevant memory information
    """
    return await _smart_search_memory_impl(
        context.context,
        query,
        max_tokens,
        detail_level
    )
