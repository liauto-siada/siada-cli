"""Workflow objective shared by GPT-5 and GPT-6 prompts."""

# GPT-5 objective — the workflow steps, and nothing else.
# Three items were removed from this list because each one duplicated another
# section of the same prompt:
#   - "You have extensive capabilities with access to a wide range of tools..."
#     restated the CAPABILITIES section that sits directly above it.
#   - "Persist until the task is fully handled end-to-end..." was a shorter copy
#     of the Core Principles bullet in rules_gpt5._get_gpt5_rules_section.
#   - "Unless the user explicitly asks for a plan..." was a shorter copy of the
#     autonomy_rule in that same function.
# Behaviour belongs to RULES; the objective only describes how to work a task.
GPT5_OBJECTIVE = """# OBJECTIVE

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.

1. Analyze the user's task and set clear, achievable goals. Prioritize them in logical order.
2. Work through these goals sequentially, utilizing available tools as necessary. Each goal should correspond to a distinct step in your problem-solving process.

"""
