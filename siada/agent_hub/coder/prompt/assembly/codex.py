"""Codex-style model instructions followed by explicit runtime fragments."""

from ..models.gpt6.templates import get_gpt6_template
from ..sections.rules.shared import _GIT_SAFETY_SECTION, _HARNESS_SECTION, _OWASP_RULE


def render_codex_system_prompt(
    *, model_name: str | None, cwd: str, os_name: str, home_dir: str,
    capabilities: str, interactive_mode: bool,
    username: str | None, preferred_language: str | None,
    skills_section: str | None, agents_section: str | None, user_memory: str | None,
) -> str:
    """Select fixed model instructions and append only supplied session facts."""
    sections = [get_gpt6_template(model_name), capabilities.strip()]
    runtime = [
        "# Runtime instructions",
        "Use `read_file` to inspect files and `apply_patch` for text-file changes. "
        "Never use shell or Python write commands when a patch can express the change.",
        _GIT_SAFETY_SECTION,
        _HARNESS_SECTION,
        _OWASP_RULE,
        "## Verification\n\nFollow explicit user and repository verification requirements. "
        "Complete required checks before reporting success, even when the model template's "
        "default is to run tests only on request. Never claim that an unrun check passed.",
    ]
    if not interactive_mode:
        runtime.append(
            "## Interaction mode\n\nThis session is non-interactive, so you cannot ask the user anything. "
            "Complete authorized work autonomously. When approval or a missing decision is required, "
            "state the blocker in the final response; do not infer approval from elapsed time."
        )
    sections.append("\n\n".join(runtime))
    environment = [
        "# SYSTEM INFORMATION", f"Operating System: {os_name}",
        f"Home Directory: {home_dir}",
        f"Current Working Directory: {cwd} (all tools execute from this directory)",
    ]
    if username:
        environment.append(f"The current user is {username}.")
    sections.append("\n\n".join(environment))
    if preferred_language is not None:
        sections.append(f"# PREFERRED LANGUAGE\n\nSpeak in {preferred_language}.")
    if skills_section and skills_section.strip():
        catalog = skills_section.partition("\n### How to use skills")[0].strip()
        sections.append(catalog)
    if agents_section and agents_section.strip():
        sections.append(agents_section.strip())
    if user_memory and user_memory.strip():
        sections.append(f"# Combined Memory\n\n{user_memory.strip()}")
    return "\n\n".join(sections) + "\n"
