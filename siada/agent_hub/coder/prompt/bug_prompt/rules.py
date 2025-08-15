def get_rules_section(cwd: str, os_name: str, home_dir: str, is_minimal:bool=False) -> str:
    """
    获取 RULES 部分的内容
    
    Args:
        cwd: 当前工作目录路径
        os_name: 操作系统名称
        home_dir: 用户主目录路径
        
    Returns:
        str: RULES 部分的文本内容
    """
    if is_minimal:
        minimal_rules = """
            - When solving problems, prioritize using the existing code block, functions and tool methods of the target project rather than reimplementing the same functionality.
                --Prioritize the Project's Existing Tools: Before writing new code, familiarize yourself with the project's existing functions, classes, and helper methods. The most efficient and stable solutions often come from leveraging the tools that are already in place, rather than reinventing the wheel.
                --Solve the Root Problem, Not Just the Symptom: Dig deeper than the surface-level issue. For example, instead of patching a complex error message after it's generated, consider if you can modify the underlying code structure (like the Abstract Syntax Tree, or AST) so that the framework's existing reporting mechanisms handle the problem automatically.
                --Align with the Framework's Philosophy: Understand the core principles of the framework you're working in. The most effective solutions often embrace the framework's inherent mechanisms. This ensures your changes are robust and consistent with the rest of the codebase.
            - When using a specific format, e.g., for date-time strings, refer to existing examples and references within the project's directory ({cwd}) to ensure your implementation is consistent. 
            - You need ensure that the modified code does not throw new exceptions.
            - you can try to use the test in original codebase to reproduce the bug.
            - You need to **create and pass test cases** that cover the following scenarios:
                --Normal Functionality: Testing the core, expected behavior of the class methods.
                --Edge Cases: Checking the behavior of methods with boundary values, such as empty lists, zero values, or maximum limits.
                --State and Attribute Changes: Ensuring that the internal state and attributes of an object are updated correctly after a method is called.
                --Uninitialized Attributes: Testing how the class behaves when an attribute is accessed before it has been explicitly assigned a value.
                --Data Types and Format: Validating that the class methods accept and process the correct data types and reject incorrect ones.
            - Deep Root Cause Analysis: Don't just patch symptoms. You must trace the bug's origin, whether it stems from a flawed assumption, an incomplete logical condition, or an unhandled edge case. Your job is to understand why the problem occurs, not just where.
            - Surgical Precision: Apply fixes with the highest level of accuracy. Your changes should be minimal and localized. This often means:
                --Adding a more precise conditional check.
                --Constraining a loop or iteration's boundary.
                --Preventing an incorrect type conversion or improper simplification.
                --Using the most suitable underlying primitive or data structure for the task.
            - Robustness and Compatibility: Your solutions must be resilient. A fix should not only resolve the reported issue but also handle all related edge cases and invalid inputs gracefully to prevent regression. Your changes must also be fully compatible with the existing code, introducing no unintended side effects.
            - Maintain Code Integrity: Your work is meant to enhance the project, not disrupt it.
                --Preserve Functionality: Ensure no existing features or valid use cases are unintentionally altered or broken.
                --Test-Driven Validation: If you need to write tests to validate a fix, they must be new and specifically designed to reproduce and verify the original bug. Never modify existing tests.   
        """
    else:
        minimal_rules=""

    return f"""RULES

- Before starting the actual work, please first understand the user's task and make a plan.
- Your current working directory is: {cwd}
- You cannot cd into a different directory to complete a task. You are stuck operating from '{cwd}', so be sure to pass in the correct 'path' parameter when using tools that require a path.
- Do not use the ~ character or $HOME to refer to the home directory.
- Before using the execute_command tool, you must first think about the SYSTEM INFORMATION context provided to understand the user's environment and tailor your commands to ensure they are compatible with their system. You must also consider if the command you need to run should be executed in a specific directory outside of the current working directory '{cwd}', and if so prepend with cd'ing into that directory && then executing the command (as one command since you are stuck operating from '{cwd}'). For example, if you needed to run npm install in a project outside of '{cwd}', you would need to prepend with a cd i.e. pseudocode for this would be cd (path to project) && (command, in this case npm install).
- You should frequently use the compress_context_tool to summarize historical messages, aiming to keep your message history as concise and accurate as possible.
- When using the regex_search_files tool, craft your regex patterns carefully to balance specificity and flexibility. Based on the user's task you may use it to find code patterns, TODO comments, function definitions, or any text-based information across the project. The results include context, so analyze the surrounding code to better understand the matches. Leverage the regex_search_files tool in combination with other tools for more comprehensive analysis. For example, use it to find specific code patterns, then use the view command of the edit_file tool to examine the full context of interesting matches before using replace_in_file to make informed changes. If your search returns too many results (more than 20), you must use the compress_context_tool to compress and summarize the search results.
- When making changes to code, always consider the context in which the code is being used. Ensure that your changes are compatible with the existing codebase and that they follow the project's coding standards and best practices.
- When you want to modify a file, use the str_replace or insert command of the edit_file tool directly with the desired changes. You do not need to display the changes before using the tool.
- When executing commands, if you don't see the expected output, assume the terminal executed the command successfully and proceed with the task. 
- When using the command str_replace of the edit_file tool, if you use multiple old_str/new_str blocks, list them in the order they appear in the file. For example if you need to make changes to both line 10 and line 50, first include the old_str/new_str block for line 10, followed by the the old_str/new_str block for line 50.
- Please fix the bug while simultaneously performing comprehensive edge testing to identify and address all boundary conditions, extreme scenarios, exceptional cases, null/empty inputs, maximum/minimum values, invalid data types, concurrent access issues, and resource constraints, ensuring your fix handles not only the reported issue but also all discovered edge cases properly.
- After completing the fix, validate that the entire system works correctly under all conditions by running thorough tests on both the original bug and all identified edge cases, providing test results that demonstrate everything functions as expected without breaking any existing functionality.
- When ANY bug fixing task is complete, you MUST call the fix_attempt_completion tool. This applies to ALL tasks, even simple ones. This is the ONLY way to properly finish and exit the execution loop. Do NOT end your response without calling this tool.

- You are not allowed to ask questions to the user, generate commands requiring user input, or any other similar interactions. Each task must be completed independently. 
- Avoid retrieving previous code versions via Git to infer the cause of the issue — the current version provides sufficient information for diagnosis.

{minimal_rules}

====

SYSTEM INFORMATION

Operating System: {os_name}
Home Directory: {home_dir}
Current Working Directory: {cwd}

===="""
