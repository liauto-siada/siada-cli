"""Compose literal Codex prompt sections with explicit per-model differences.

Template selection preserves complete upstream sections and per-model prose.
"""

from functools import lru_cache
from pathlib import Path
import re
import tomllib

from ...selection.model_features import uses_gpt6_scannable_writing_style


_TEMPLATES_DIR = Path(__file__).parent / "templates"
_SECTION_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_DIRECTIVE = re.compile(r"\{\{(include|value):([a-z0-9]+(?:[-_][a-z0-9]+)*)\}\}")


def _render_gpt6_template(template_name: str) -> str:
    """Render one common section order with defaults, group and model overrides."""
    specification = tomllib.loads((_TEMPLATES_DIR / "composition.toml").read_text(encoding="utf-8"))
    if template_name not in specification["models"]:
        raise ValueError(f"Unknown GPT-6 prompt template: {template_name}")
    model = specification["models"][template_name]
    group_name = model.get("group")
    if group_name is not None and group_name not in specification.get("groups", {}):
        raise ValueError(f"Unknown GPT-6 prompt group: {group_name}")
    group = specification["groups"][group_name] if group_name is not None else {}
    fragments: dict[str, str] = {}
    values: dict[str, str] = {}
    for layer in (specification["defaults"], group, model):
        fragments.update(layer.get("fragments", {}))
        values.update(layer.get("values", {}))

    def render_section(section_name: str, stack: tuple[str, ...] = ()) -> str:
        if not isinstance(section_name, str) or _SECTION_NAME.fullmatch(section_name) is None:
            raise ValueError(f"Invalid GPT-6 shared prompt section name: {section_name}")
        if section_name in stack:
            raise ValueError(f"Cyclic GPT-6 shared prompt include: {' -> '.join((*stack, section_name))}")
        stack = (*stack, section_name)
        if section_name in fragments:
            selected = fragments[section_name]
            if not isinstance(selected, str):
                raise ValueError(f"GPT-6 prompt fragment must be a section name or empty text: {section_name}")
            return render_section(selected, stack) if selected else ""

        section_path = _TEMPLATES_DIR / "shared" / f"{section_name}.md"
        try:
            section = section_path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise ValueError(f"Unknown GPT-6 shared prompt section: {section_name}") from error

        def replace_directive(match: re.Match[str]) -> str:
            kind, name = match.groups()
            if kind == "include":
                return render_section(name, stack)
            if name not in values:
                raise ValueError(f"Unknown GPT-6 prompt value: {name} in {section_name}")
            value = values[name]
            if not isinstance(value, str):
                raise ValueError(f"GPT-6 prompt value must be text: {name}")
            return value

        # Parent sections own the separators; preserve all other literal bytes.
        expanded = _DIRECTIVE.sub(replace_directive, section.removesuffix("\n"))
        if "{{include:" in expanded or "{{value:" in expanded:
            raise ValueError(f"Invalid GPT-6 prompt directive in section: {section_name}")
        return expanded

    composition = specification["composition"]
    sections = [render_section(name) for name in composition["sections"]]
    return "\n\n".join(section for section in sections if section) + composition["suffix"]


def resolve_gpt6_template_name(model_name: str | None) -> str:
    lowered = str(model_name or "").lower()
    if re.search(r"(?:^|[^a-z0-9])gpt[-_]?6\.1[-_./\s]+sol(?:$|[^a-z0-9])", lowered):
        return "gpt-6.1-sol"
    if uses_gpt6_scannable_writing_style(model_name):
        return "gpt-6-luna" if "luna" in re.split(r"[-_.\s/]+", lowered) else "gpt-6-sol"
    return "gpt-6-astra"


@lru_cache(maxsize=4)
def load_gpt6_template(template_name: str) -> str:
    return _render_gpt6_template(template_name).strip()


def get_gpt6_template(model_name: str | None) -> str:
    return load_gpt6_template(resolve_gpt6_template_name(model_name))
