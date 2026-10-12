"""Shared-section expansion must preserve the reviewed per-model prompt bytes."""

import hashlib
import re
import tomllib
from collections import defaultdict

import pytest

from siada.agent_hub.coder.prompt.models.gpt6 import templates


# Reviewed template bytes after removing unsupported question-tool guidance.
# Do not regenerate these hashes as part of a structural refactor.
EXPECTED_TEMPLATE_SHA256 = {
    "gpt-6-astra": "b0196c4f0184707e66bcd7bf7e4eb2230ea397c59a1c66db1fdf2aaf5cc73ac5",
    "gpt-6-luna": "838c23accb9eae215017c41d347b0ff6e1c42093462ad90318eb356293349a31",
    "gpt-6-sol": "74a14e6eb7736485b77c5beed1b002b270df927874cea667af69bdf6992744ae",
    "gpt-6.1-sol": "2cf311504e94a9e5e13f7171a99bfcf4bf5ab484a4f69cafaa6908b680492cd9",
}


@pytest.fixture(autouse=True)
def clear_template_cache():
    templates.load_gpt6_template.cache_clear()
    yield
    templates.load_gpt6_template.cache_clear()


@pytest.fixture
def template_files(monkeypatch, tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    monkeypatch.setattr(templates, "_TEMPLATES_DIR", tmp_path)

    def write_template(text, sections=None, *, specification=None):
        specification = specification or '''
[composition]
sections = ["root"]
suffix = "\\n\\n"
[defaults.fragments]
[defaults.values]
[models.gpt-6-astra]
'''
        (tmp_path / "composition.toml").write_text(specification, encoding="utf-8")
        (shared / "root.md").write_text(text, encoding="utf-8")
        for name, content in (sections or {}).items():
            (shared / f"{name}.md").write_text(content, encoding="utf-8")

    return write_template


@pytest.mark.parametrize("template_name, expected_hash", EXPECTED_TEMPLATE_SHA256.items())
def test_expanded_templates_match_reviewed_bytes(template_name, expected_hash):
    expanded = templates._render_gpt6_template(template_name)
    rendered = templates.load_gpt6_template(template_name)
    assert "{{include:" not in rendered
    assert "{{value:" not in rendered
    assert hashlib.sha256(expanded.encode("utf-8")).hexdigest() == expected_hash
    assert rendered == expanded.strip()


def test_shared_sections_preserve_internal_whitespace_and_literal_text(template_files):
    template_files(
        "\nBefore\n\n{{include:one}}\n\n\n{{include:two}}\n\nAfter\n",
        {
            "one": "# Shared\n\n  Indented 中文 `$()` {literal}\n\n",
            "two": "No final newline",
        },
    )
    assert templates.load_gpt6_template("gpt-6-astra") == (
        "Before\n\n# Shared\n\n  Indented 中文 `$()` {literal}"
        "\n\n\n\nNo final newline\n\nAfter"
    )


@pytest.mark.parametrize("template_name", ["gpt-6-nova", "../gpt-6-astra", ""])
def test_unknown_template_is_rejected(template_name):
    with pytest.raises(ValueError, match="Unknown GPT-6 prompt template"):
        templates.load_gpt6_template(template_name)


def test_missing_shared_section_names_the_missing_section(template_files):
    template_files("{{include:missing-section}}\n")
    with pytest.raises(ValueError, match="Unknown GPT-6 shared prompt section: missing-section"):
        templates.load_gpt6_template("gpt-6-astra")


@pytest.mark.parametrize("include", [
    "{{include:../identity}}",
    "{{include:/identity}}",
    "{{include:identity.md}}",
    "{{include:}}",
    "{{include:identity_name}}",
    "{{value:}}",
    "{{value:../unsafe}}",
])
def test_malformed_shared_include_is_rejected(template_files, include):
    template_files(include + "\n")
    with pytest.raises(ValueError, match="Invalid GPT-6 (prompt directive|shared prompt section name)"):
        templates.load_gpt6_template("gpt-6-astra")


def test_nested_and_inline_sections_preserve_word_and_paragraph_boundaries(template_files):
    template_files("Before {{include:outer}} after.\n", {
        "outer": "{{include:inner}}\n\n# Nested\n",
        "inner": "nested 中文 `$()` {literal}\n",
    })
    assert templates.load_gpt6_template("gpt-6-astra") == (
        "Before nested 中文 `$()` {literal}\n\n# Nested after."
    )


@pytest.mark.parametrize("sections, cycle", [
    ({"outer": "{{include:outer}}\n"}, "root -> outer -> outer"),
    ({"outer": "{{include:inner}}\n", "inner": "{{include:outer}}\n"}, "root -> outer -> inner -> outer"),
])
def test_cyclic_sections_report_the_reference_chain(template_files, sections, cycle):
    template_files("{{include:outer}}\n", sections)
    with pytest.raises(ValueError, match=re.escape(f"Cyclic GPT-6 shared prompt include: {cycle}")):
        templates.load_gpt6_template("gpt-6-astra")


def test_defaults_group_and_model_overrides_have_explicit_precedence(template_files):
    template_files("{{include:choice}}/{{value:label}}\n", {
        "first": "Default\n", "second": "Group\n", "third": "Model\n",
    }, specification='''
[composition]
sections = ["root", "optional"]
suffix = "\\n\\n"
[defaults.fragments]
choice = "first"
optional = ""
[defaults.values]
label = "Default"
[groups.concise.fragments]
choice = "second"
[groups.concise.values]
label = "Group"
[models.gpt-6-astra]
[models.gpt-6-sol]
group = "concise"
[models.gpt-6-luna]
group = "concise"
[models.gpt-6-luna.fragments]
choice = "third"
[models.gpt-6-luna.values]
label = "Model"
''')
    assert templates.load_gpt6_template("gpt-6-astra") == "Default/Default"
    assert templates.load_gpt6_template("gpt-6-sol") == "Group/Group"
    assert templates.load_gpt6_template("gpt-6-luna") == "Model/Model"


def test_fragment_aliases_cannot_create_a_cycle(template_files):
    template_files("{{include:alias}}\n", specification='''
[composition]
sections = ["root"]
suffix = ""
[defaults.fragments]
alias = "root"
[models.gpt-6-astra]
''')
    with pytest.raises(ValueError, match="root -> alias -> root"):
        templates.load_gpt6_template("gpt-6-astra")


def test_unknown_group_is_not_silently_replaced_by_defaults(template_files):
    template_files("Literal\n", specification='''
[composition]
sections = ["root"]
suffix = ""
[defaults.fragments]
[models.gpt-6-astra]
group = "missing"
''')
    with pytest.raises(ValueError, match="Unknown GPT-6 prompt group: missing"):
        templates.load_gpt6_template("gpt-6-astra")


def test_unknown_value_names_the_owning_section(template_files):
    template_files("{{value:missing}}\n")
    with pytest.raises(ValueError, match="Unknown GPT-6 prompt value: missing in root"):
        templates.load_gpt6_template("gpt-6-astra")


def test_values_are_literal_text_not_a_second_template_pass(template_files):
    template_files("{{value:content}}\n", specification='''
[composition]
sections = ["root"]
suffix = ""
[defaults.values]
content = "{{include:unexpected}}"
[models.gpt-6-astra]
''')
    with pytest.raises(ValueError, match="Invalid GPT-6 prompt directive in section: root"):
        templates.load_gpt6_template("gpt-6-astra")


def test_numeric_value_is_rejected_instead_of_changing_literal_prompt_text(template_files):
    template_files("{{value:wait}}\n", specification='''
[composition]
sections = ["root"]
suffix = ""
[defaults.values]
wait = 30
[models.gpt-6-astra]
''')
    with pytest.raises(ValueError, match="GPT-6 prompt value must be text: wait"):
        templates.load_gpt6_template("gpt-6-astra")


def test_prompt_sources_do_not_duplicate_complete_prose_rules():
    """Audit author-owned sources, not the intentionally repeated rendered prompts."""
    specification = tomllib.loads((templates._TEMPLATES_DIR / "composition.toml").read_text(encoding="utf-8"))
    sources = {path.name: path.read_text(encoding="utf-8")
               for path in (templates._TEMPLATES_DIR / "shared").glob("*.md")}
    layers = [("defaults", specification["defaults"])]
    layers.extend(specification.get("groups", {}).items())
    layers.extend(specification["models"].items())
    for layer_name, layer in layers:
        for key, value in layer.get("values", {}).items():
            sources[f"{layer_name}.{key}"] = value

    owners = defaultdict(set)
    for source, text in sources.items():
        # Template markers are references, not independently maintained prose.
        literal = re.sub(r"\{\{(?:include|value):[^}]+\}\}", "\n", text)
        units = re.split(r"\n\n+|(?<=[.!?])\s+(?=[A-Z][a-z])", literal)
        units.extend(line for line in literal.splitlines() if line.startswith("- "))
        for unit in units:
            unit = unit.strip()
            if unit:
                owners[unit].add(source)
    duplicated = {unit: sorted(paths) for unit, paths in owners.items() if len(paths) > 1}
    assert not duplicated, duplicated


def test_all_shared_sections_are_reachable_by_supported_profiles(monkeypatch):
    visited = set()
    original = templates.Path.read_text

    def recording_read(path, *args, **kwargs):
        if path.parent == templates._TEMPLATES_DIR / "shared":
            visited.add(path.name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(templates.Path, "read_text", recording_read)
    for name in EXPECTED_TEMPLATE_SHA256:
        templates.load_gpt6_template(name)
    assert visited == {path.name for path in (templates._TEMPLATES_DIR / "shared").glob("*.md")}


def test_settings_and_overrides_are_used_and_not_redundant():
    specification = tomllib.loads((templates._TEMPLATES_DIR / "composition.toml").read_text(encoding="utf-8"))
    all_text = "\n".join(path.read_text(encoding="utf-8")
                         for path in (templates._TEMPLATES_DIR / "shared").glob("*.md"))
    references = {
        "fragments": set(specification["composition"]["sections"])
                     | set(re.findall(r"\{\{include:([^}]+)\}\}", all_text)),
        "values": set(re.findall(r"\{\{value:([^}]+)\}\}", all_text)),
    }
    defaults = specification["defaults"]
    groups = specification.get("groups", {})
    used_groups = {model.get("group") for model in specification["models"].values()}
    assert set(groups) <= used_groups
    layers = [("defaults", defaults, {})]
    layers.extend((name, group, defaults) for name, group in groups.items())
    for name, model in specification["models"].items():
        group = groups.get(model.get("group"), {})
        inherited = {kind: {**defaults.get(kind, {}), **group.get(kind, {})}
                     for kind in references}
        layers.append((name, model, inherited))
    for name, layer, inherited in layers:
        for kind, used in references.items():
            for key, value in layer.get(kind, {}).items():
                assert key in used, f"Unused {name}.{kind}.{key}"
                assert key not in inherited.get(kind, {}) or value != inherited[kind][key], (
                    f"Redundant override: {name}.{kind}.{key}"
                )
