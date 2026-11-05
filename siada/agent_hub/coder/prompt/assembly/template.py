from collections.abc import Mapping
from string import Template


def render_prompt_template(template: str, values: Mapping[str, object]) -> str:
    """Substitute runtime values once without normalizing any template bytes."""
    return Template(template).substitute(values)


def render_optional_section(
    content: str | None, *, prefix: str = "", suffix: str = "", strip: bool = True,
) -> str:
    if not content or not content.strip():
        return ""
    body = content.strip() if strip else content
    return f"{prefix}{body}{suffix}"
