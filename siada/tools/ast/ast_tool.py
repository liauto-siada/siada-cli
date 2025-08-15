"""
Code tag extraction utilities using tree-sitter and pygments.

This module provides functionality to extract definitions and references
from source code files using tree-sitter parsing with pygments fallback.
"""

import warnings
from pathlib import Path
from typing import Generator, List, Optional

from agents import function_tool
from grep_ast import TreeContext, filename_to_lang
from pygments.lexers import guess_lexer_for_filename
from pygments.token import Token

from siada.tools.coder.observation.observation import FunctionCallResult

from .models import Tag

# tree_sitter is throwing a FutureWarning
warnings.simplefilter("ignore", category=FutureWarning)
from grep_ast.tsl import USING_TSL_PACK, get_language, get_parser  # noqa: E402

class ListCodeDefinitionNamesResult(FunctionCallResult):
    """This data class represents the output of a list code definition names operation."""

    def __init__(self, content: str):
        self.content = content

    def format_for_display(self):
        return str(self)

    def __str__(self):
        return self.content
    

@function_tool(name_override="list_code_definition_names")
def list_code_definition_names(file_name: str, rel_file_name: Optional[str] = None) -> str:
    """
    Analyze a source code file and extract its structural definitions.

    This function performs static code analysis to identify and extract code definitions
    such as functions, classes, methods, and variables from a source file. It uses
    tree-sitter parsing technology to build an Abstract Syntax Tree (AST) and then
    queries the tree to locate definition nodes. The extracted information is formatted
    into a human-readable tree structure that shows the code organization and hierarchy.

    The implementation follows a two-phase approach: first, it parses the source code
    to extract both definitions and references using language-specific query patterns;
    second, it formats the definitions into a contextual tree view that preserves the
    original code structure and provides line number information for easy navigation.

    Args:
        file_name: Absolute path to the source file to analyze
        rel_file_name: Relative path to the source file (optional, defaults to filename)

    Returns:
        Formatted string containing:
        - File summary with definition and reference counts
        - Hierarchical tree view of code definitions with context
    """
    content = _list_code_definition_names(file_name, rel_file_name)
    return ListCodeDefinitionNamesResult(content)

def get_scm_fname(lang: str) -> Optional[Path]:
    """
    Get the path to the tree-sitter query file for a given language.
    
    Args:
        lang: Programming language identifier
        
    Returns:
        Path to the .scm query file, or None if not found
    """
    # Find the project root by looking for the queries directory
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent  # Go up to siada/ level
    queries_dir = project_root / "queries"
    
    if USING_TSL_PACK:
        subdir = "tree-sitter-language-pack"
        path = queries_dir / subdir / f"{lang}-tags.scm"
        if path.exists():
            return path

    # Fall back to tree-sitter-languages
    subdir = "tree-sitter-languages"
    path = queries_dir / subdir / f"{lang}-tags.scm"
    if path.exists():
        return path
        
    # If not found, return None
    return None


def get_tags_raw(fname: str, rel_fname: str) -> Generator[Tag, None, None]:
    """
    Extract code tags (definitions and references) from a source file.
    
    This function uses tree-sitter to parse source code and extract identifiers,
    with pygments as a fallback for reference extraction when tree-sitter
    queries only provide definitions.
    
    Args:
        fname: Absolute path to the source file
        rel_fname: Relative path to the source file
        
    Yields:
        Tag: Named tuple containing identifier information with fields:
            - rel_fname: relative file path
            - fname: absolute file path  
            - name: identifier name
            - kind: "def" for definitions, "ref" for references
            - line: line number (0-based, -1 for pygments fallback)
    """
    lang = filename_to_lang(fname)
    if not lang:
        return

    try:
        language = get_language(lang)
        parser = get_parser(lang)
    except Exception as err:
        print(f"Skipping file {fname}: {err}")
        return

    query_scm = get_scm_fname(lang)
    if not query_scm or not query_scm.exists():
        return
    query_scm_content = query_scm.read_text()

    try:
        with open(fname, 'r', encoding='utf-8') as f:
            code = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"Error reading file {fname}: {e}")
        return
        
    if not code:
        return
    tree = parser.parse(bytes(code, "utf-8"))

    # Run the tags queries
    query = language.query(query_scm_content)
    captures = query.captures(tree.root_node)

    saw = set()
    if USING_TSL_PACK:
        all_nodes = []
        for tag, nodes in captures.items():
            all_nodes += [(node, tag) for node in nodes]
    else:
        all_nodes = list(captures)

    for node, tag in all_nodes:
        if tag.startswith("name.definition."):
            kind = "def"
        elif tag.startswith("name.reference."):
            kind = "ref"
        else:
            continue

        saw.add(kind)

        result = Tag(
            rel_fname=rel_fname,
            fname=fname,
            name=node.text.decode("utf-8"),
            kind=kind,
            line=node.start_point[0],
        )

        yield result

    if "ref" in saw:
        return
    if "def" not in saw:
        return

    # We saw defs, without any refs
    # Some tags files only provide defs (cpp, for example)
    # Use pygments to backfill refs

    try:
        lexer = guess_lexer_for_filename(fname, code)
    except Exception:  # On Windows, bad ref to time.clock which is deprecated?
        return

    tokens = list(lexer.get_tokens(code))
    tokens = [token[1] for token in tokens if token[0] in Token.Name]

    for token in tokens:
        yield Tag(
            rel_fname=rel_fname,
            fname=fname,
            name=token,
            kind="ref",
            line=-1,
        )


def to_tree(tags: List[Tag]) -> str:
    """
    Convert a list of tags to a formatted code tree structure (single file scenario).
    
    This function is optimized for single file analysis, without caching mechanisms.
    It focuses on definitions and provides code context using TreeContext.
    
    Args:
        tags: List of Tag objects from a single file
        
    Returns:
        Formatted string containing code structure with context
    """
    if not tags:
        return ""
    
    # Filter only definition tags and sort by line number
    def_tags = [tag for tag in tags if tag.kind == "def"]
    if not def_tags:
        return ""
    
    def_tags.sort(key=lambda t: t.line)
    
    # Get file info from first tag
    rel_fname = def_tags[0].rel_fname
    abs_fname = def_tags[0].fname
    
    # Read file content
    try:
        with open(abs_fname, 'r', encoding='utf-8') as f:
            code = f.read()
    except (OSError, UnicodeDecodeError) as e:
        return f"Error reading file {abs_fname}: {e}"
    
    if not code:
        return ""
    
    # Ensure code ends with newline
    if not code.endswith("\n"):
        code += "\n"
    
    # Create TreeContext for extracting code context
    try:
        context = TreeContext(
            rel_fname,
            code,
            color=False,
            line_number=False,
            child_context=False,
            last_line=False,
            margin=0,
            mark_lois=False,
            loi_pad=0,
            show_top_of_file_parent_scope=False,
        )
        
        # Add all definition lines as lines of interest
        lois = [tag.line for tag in def_tags if tag.line >= 0]
        context.add_lines_of_interest(lois)
        context.add_context()
        
        # Format the result
        result = context.format()
        
        # Truncate long lines to prevent excessive output
        output_lines = []
        for line in result.splitlines():
            if len(line) > 100:
                output_lines.append(line[:100] + "...")
            else:
                output_lines.append(line)
        
        return "\n".join(output_lines) + "\n"
        
    except Exception as e:
        # Fallback: simple list of definitions
        output = f"{rel_fname}:\n"
        for tag in def_tags:
            output += f"  {tag.name} (line {tag.line + 1})\n"
        return output


def _list_code_definition_names(fname: str, rel_fname: Optional[str] = None) -> str:
    """
    Analyze a source code file and extract its structural definitions.
    
    This function performs static code analysis to identify and extract code definitions
    such as functions, classes, methods, and variables from a source file. It uses 
    tree-sitter parsing technology to build an Abstract Syntax Tree (AST) and then 
    queries the tree to locate definition nodes. The extracted information is formatted 
    into a human-readable tree structure that shows the code organization and hierarchy.
    
    The implementation follows a two-phase approach: first, it parses the source code 
    to extract both definitions and references using language-specific query patterns; 
    second, it formats the definitions into a contextual tree view that preserves the 
    original code structure and provides line number information for easy navigation.
    
    Args:
        fname: Absolute path to the source file to analyze
        rel_fname: Relative path to the source file (optional, defaults to filename)
        
    Returns:
        Formatted string containing:
        - File summary with definition and reference counts
        - Hierarchical tree view of code definitions with context
        - Line numbers for each definition
        - Fallback to simple list format if tree generation fails
    """
    if rel_fname is None:
        rel_fname = Path(fname).name
    
    # Extract tags from the file
    tags = list(get_tags_raw(fname, rel_fname))
    
    if not tags:
        return f"No code definitions found in {rel_fname}"
    
    # Get definitions count
    definitions = [tag for tag in tags if tag.kind == "def"]
    references = [tag for tag in tags if tag.kind == "ref"]
    
    # Generate header with summary
    header = f"File: {rel_fname}\n"
    header += f"Definitions: {len(definitions)}, References: {len(references)}\n\n"
    
    # Generate code tree
    tree_output = to_tree(tags)
    
    if tree_output.strip():
        return header + tree_output
    else:
        # Fallback: simple list
        if definitions:
            result = header + "Definitions found:\n"
            for tag in sorted(definitions, key=lambda t: t.line):
                result += f"  - {tag.name} (line {tag.line + 1})\n"
            return result
        else:
            return header + "No definitions found in this file."
