from ..sections.memory import wrap_user_memory
from ..sections.rules.shared import _GIT_SAFETY_SECTION, _HARNESS_SECTION, _OWASP_RULE


_EDIT_FILE_INSTRUCTION = (
    "Use `edit_file` to inspect files and make text-file changes. "
    "Never use shell or Python write commands when the dedicated file tool can express the change."
)
_NATIVE_PATCH_INSTRUCTION = (
    "Use `read_file` to inspect files and `apply_patch` for text-file changes. "
    "Never use shell or Python write commands when a patch can express the change."
)
_INTERACTION_MODE = (
    "## Interaction mode\n\nThis session is non-interactive, so you cannot ask the user anything. "
    "Complete authorized work autonomously. When approval or a missing decision is required, "
    "state the blocker in the final response; do not infer approval from elapsed time."
)


def render_runtime_instructions(
    *, interactive_mode: bool, native_patch: bool = False, extra_sections: tuple[str, ...] = (),
) -> str:
    sections = [
        "# Runtime instructions",
        _NATIVE_PATCH_INSTRUCTION if native_patch else _EDIT_FILE_INSTRUCTION,
        _GIT_SAFETY_SECTION,
        _HARNESS_SECTION,
        _OWASP_RULE,
        *extra_sections,
    ]
    if not interactive_mode:
        sections.append(_INTERACTION_MODE)
    return "\n\n".join(sections)


def get_skills_catalog(skills_section: str | None) -> str:
    if not skills_section or not skills_section.strip():
        return ""
    return skills_section.partition("\n### How to use skills")[0].strip()


def render_memory_section(user_memory: str | None, *, bounded: bool = True) -> str:
    if not user_memory or not user_memory.strip():
        return ""
    if bounded:
        return wrap_user_memory(user_memory)
    return f"# Combined Memory\n\n{user_memory.strip()}"
