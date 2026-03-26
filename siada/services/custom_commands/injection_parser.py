"""
Parser for injection syntax (@{...} and !{...})

Uses balanced bracket counting to parse nested structures.
"""

from typing import List, NamedTuple


class Injection(NamedTuple):
    """Represents a single injection block in the prompt"""
    content: str  # Content inside the brackets (trimmed)
    start_index: int  # Starting position (including trigger)
    end_index: int  # Ending position (including closing '}')


def extract_injections(
    prompt: str,
    trigger: str,
    context_name: str = ""
) -> List[Injection]:
    """
    Extract all injection blocks from a prompt string.
    
    Args:
        prompt: The prompt text to parse
        trigger: The trigger string ('!{' or '@{')
        context_name: Optional context name for error messages
        
    Returns:
        List of Injection objects
        
    Raises:
        ValueError: If brackets are unbalanced
    """
    injections: List[Injection] = []
    index = 0
    
    while index < len(prompt):
        # Find next trigger
        start_index = prompt.find(trigger, index)
        if start_index == -1:
            break
            
        # Count brackets to find matching closing brace
        current_index = start_index + len(trigger)
        brace_count = 1  # trigger already contains one '{'
        found_end = False
        
        while current_index < len(prompt):
            char = prompt[current_index]
            
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                
                if brace_count == 0:
                    # Found matching closing brace
                    content = prompt[start_index + len(trigger):current_index].strip()
                    
                    injections.append(Injection(
                        content=content,
                        start_index=start_index,
                        end_index=current_index + 1  # Include the closing '}'
                    ))
                    
                    index = current_index + 1
                    found_end = True
                    break
                    
            current_index += 1
        
        # If we didn't find a closing brace, it's an error
        if not found_end:
            context = f" in command '{context_name}'" if context_name else ""
            raise ValueError(
                f"Invalid syntax{context}: Unclosed injection starting at "
                f"index {start_index} ('{trigger}'). Ensure braces are balanced."
            )
    
    return injections
