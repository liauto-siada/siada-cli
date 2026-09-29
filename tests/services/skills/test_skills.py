"""
Tests for siada/services/skills module
"""

import logging
import tempfile
import pytest
from pathlib import Path

from siada.services.skills import (
    SkillScope,
    SkillUsageProfile,
    SkillMetadata,
    SkillError,
    SkillLoadOutcome,
    SkillParseError,
    SkillsManager,
    render_skills_section,
    render_skill_summary,
    discover_skill_dirs,
    parse_skill_file,
    load_skills_from_roots,
    get_skill_roots,
    SKILL_FILENAME,
)


# ============================================================================
# Test Data
# ============================================================================

VALID_SKILL_CONTENT = """---
name: test-skill
description: A test skill for unit testing purposes
metadata:
  short-description: Test skill
---

# Test Skill

This is a test skill.

## Workflow

1. Do something
2. Do something else
"""

SKILL_MISSING_NAME = """---
description: Missing name field
---

# Missing Name
"""

SKILL_MISSING_DESC = """---
name: no-desc
---

# No Description
"""

SKILL_INVALID_FRONTMATTER = """
No frontmatter here, just content.
"""


# ============================================================================
# Model Tests
# ============================================================================

class TestSkillScope:
    """Test SkillScope enum"""
    
    def test_priority_order(self):
        """Test that USER has highest priority (lowest value)"""
        assert SkillScope.USER < SkillScope.REPO < SkillScope.SYSTEM
    
    def test_values(self):
        """Test enum values"""
        assert SkillScope.USER == 0
        assert SkillScope.REPO == 1
        assert SkillScope.SYSTEM == 2


class TestSkillMetadata:
    """Test SkillMetadata dataclass"""
    
    def test_creation(self):
        """Test basic creation"""
        skill = SkillMetadata(
            name="test",
            description="test desc",
            path=Path("/test/SKILL.md"),
            scope=SkillScope.REPO,
        )
        assert skill.name == "test"
        assert skill.description == "test desc"
        assert skill.scope == SkillScope.REPO
        assert skill.short_description is None
    
    def test_equality(self):
        """Test that skills are equal if names match"""
        skill1 = SkillMetadata(
            name="test",
            description="desc1",
            path=Path("/path1/SKILL.md"),
            scope=SkillScope.REPO,
        )
        skill2 = SkillMetadata(
            name="test",
            description="desc2",
            path=Path("/path2/SKILL.md"),
            scope=SkillScope.USER,
        )
        assert skill1 == skill2
    
    def test_hash(self):
        """Test hash is based on name"""
        skill = SkillMetadata(
            name="test",
            description="desc",
            path=Path("/test/SKILL.md"),
            scope=SkillScope.REPO,
        )
        assert hash(skill) == hash("test")


class TestSkillLoadOutcome:
    """Test SkillLoadOutcome dataclass"""
    
    def test_has_errors(self):
        """Test has_errors method"""
        outcome_no_errors = SkillLoadOutcome(skills=[], errors=[])
        assert not outcome_no_errors.has_errors()
        
        outcome_with_errors = SkillLoadOutcome(
            skills=[],
            errors=[SkillError(Path("/test"), "error", SkillScope.REPO)]
        )
        assert outcome_with_errors.has_errors()
    
    def test_merge(self):
        """Test merge method"""
        skill1 = SkillMetadata("s1", "d1", Path("/1"), SkillScope.REPO)
        skill2 = SkillMetadata("s2", "d2", Path("/2"), SkillScope.USER)
        error1 = SkillError(Path("/e1"), "e1", SkillScope.REPO)
        error2 = SkillError(Path("/e2"), "e2", SkillScope.USER)
        
        outcome1 = SkillLoadOutcome(skills=[skill1], errors=[error1])
        outcome2 = SkillLoadOutcome(skills=[skill2], errors=[error2])
        
        merged = outcome1.merge(outcome2)
        assert len(merged.skills) == 2
        assert len(merged.errors) == 2


# ============================================================================
# Loader Tests
# ============================================================================

class TestLoader:
    """Test loader functions"""
    
    def test_discover_skill_dirs(self):
        """Test skill directory discovery"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create skill directories
            skill1_dir = tmppath / "skill1"
            skill1_dir.mkdir()
            (skill1_dir / SKILL_FILENAME).write_text(VALID_SKILL_CONTENT)
            
            skill2_dir = tmppath / "nested" / "skill2"
            skill2_dir.mkdir(parents=True)
            (skill2_dir / SKILL_FILENAME).write_text(VALID_SKILL_CONTENT)
            
            # Should not be discovered (no SKILL.md)
            empty_dir = tmppath / "empty"
            empty_dir.mkdir()
            
            dirs = list(discover_skill_dirs(tmppath))
            assert len(dirs) == 2
            assert skill1_dir in dirs
            assert skill2_dir in dirs
    
    def test_discover_nonexistent_dir(self):
        """Test discovery on nonexistent directory"""
        dirs = list(discover_skill_dirs(Path("/nonexistent/path")))
        assert dirs == []
    
    def test_parse_skill_file_valid(self):
        """Test parsing valid SKILL.md"""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / SKILL_FILENAME).write_text(VALID_SKILL_CONTENT)
            
            skill = parse_skill_file(skill_dir, SkillScope.REPO)
            
            assert skill.name == "test-skill"
            assert skill.description == "A test skill for unit testing purposes"
            assert skill.short_description == "Test skill"
            assert skill.scope == SkillScope.REPO
    
    def test_parse_skill_file_missing_name(self):
        """Test parsing SKILL.md without name"""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "bad-skill"
            skill_dir.mkdir()
            (skill_dir / SKILL_FILENAME).write_text(SKILL_MISSING_NAME)
            
            with pytest.raises(SkillParseError) as exc:
                parse_skill_file(skill_dir, SkillScope.REPO)
            
            assert "name" in str(exc.value).lower()
    
    def test_parse_skill_file_missing_description(self):
        """Test parsing SKILL.md without description"""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "bad-skill"
            skill_dir.mkdir()
            (skill_dir / SKILL_FILENAME).write_text(SKILL_MISSING_DESC)
            
            with pytest.raises(SkillParseError) as exc:
                parse_skill_file(skill_dir, SkillScope.REPO)
            
            assert "description" in str(exc.value).lower()
    
    def test_parse_skill_file_invalid_frontmatter(self):
        """Test parsing SKILL.md without frontmatter"""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "bad-skill"
            skill_dir.mkdir()
            (skill_dir / SKILL_FILENAME).write_text(SKILL_INVALID_FRONTMATTER)
            
            with pytest.raises(SkillParseError) as exc:
                parse_skill_file(skill_dir, SkillScope.REPO)
            
            assert "frontmatter" in str(exc.value).lower()


class TestLoadSkillsDeduplication:
    """Test skill loading with priority deduplication"""
    
    def test_same_name_priority(self):
        """Test that higher priority scope shadows lower priority"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create user skill (higher priority)
            user_root = tmppath / "user" / "skills"
            user_skill = user_root / "my-skill"
            user_skill.mkdir(parents=True)
            (user_skill / SKILL_FILENAME).write_text("""---
name: my-skill
description: User version
---
# User
""")
            
            # Create repo skill (lower priority)
            repo_root = tmppath / "repo" / ".siada" / "skills"
            repo_skill = repo_root / "my-skill"
            repo_skill.mkdir(parents=True)
            (repo_skill / SKILL_FILENAME).write_text("""---
name: my-skill
description: Repo version
---
# Repo
""")
            
            roots = {
                SkillScope.REPO: repo_root,
                SkillScope.USER: user_root,
            }
            
            outcome = load_skills_from_roots(roots)
            
            # Should only have one skill (user version)
            assert len(outcome.skills) == 1
            assert outcome.skills[0].description == "User version"
            assert outcome.skills[0].scope == SkillScope.USER


# ============================================================================
# Manager Tests
# ============================================================================

class TestSkillsManager:
    """Test SkillsManager"""
    
    def setup_method(self):
        """Reset singleton before each test"""
        SkillsManager.reset_instance()
    
    def teardown_method(self):
        """Reset singleton after each test"""
        SkillsManager.reset_instance()
    
    def test_singleton(self):
        """Test singleton pattern"""
        with tempfile.TemporaryDirectory() as tmpdir:
            siada_home = Path(tmpdir)
            
            manager1 = SkillsManager(siada_home)
            manager2 = SkillsManager(siada_home)
            
            assert manager1 is manager2
    
    def test_skills_for_cwd_cache(self):
        """Test that skills are cached per cwd"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            siada_home = tmppath / ".siada-cli"
            siada_home.mkdir()
            
            manager = SkillsManager(siada_home)
            
            cwd = tmppath / "project"
            cwd.mkdir()
            
            # First call loads skills
            outcome1 = manager.skills_for_cwd(cwd)
            
            # Second call uses cache
            outcome2 = manager.skills_for_cwd(cwd)
            
            # Should be same object (cached)
            assert outcome1 is outcome2
    
    def test_invalidate_cache(self):
        """Test cache invalidation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            siada_home = tmppath / ".siada-cli"
            siada_home.mkdir()
            
            manager = SkillsManager(siada_home)
            
            cwd = tmppath / "project"
            cwd.mkdir()
            
            outcome1 = manager.skills_for_cwd(cwd)
            manager.invalidate_cache(cwd)
            outcome2 = manager.skills_for_cwd(cwd)
            
            # Should be different objects (cache was invalidated)
            assert outcome1 is not outcome2


# ============================================================================
# Renderer Tests
# ============================================================================

class TestRenderer:
    """Test renderer functions"""
    
    def test_render_skills_section_empty(self):
        """Test rendering with no skills"""
        result = render_skills_section([])
        assert result is None
        
        result_with_hint = render_skills_section([], include_empty_hint=True)
        assert result_with_hint is not None
        assert "No skills" in result_with_hint
    
    def test_render_skills_section_with_skills(self):
        """Test rendering with skills"""
        skills = [
            SkillMetadata(
                name="skill-a",
                description="Description A",
                path=Path("/path/a/SKILL.md"),
                scope=SkillScope.REPO,
            ),
            SkillMetadata(
                name="skill-b",
                description="Description B",
                path=Path("/path/b/SKILL.md"),
                scope=SkillScope.USER,
            ),
        ]
        
        result = render_skills_section(skills)
        
        assert result is not None
        assert "skill-a" in result
        assert "skill-b" in result
        assert "Description A" in result
        assert "Description B" in result
        assert "Available skills" in result
        assert "How to use skills" in result

    def test_hidden_system_skill_is_rendered_only_when_activated(self, monkeypatch):
        """Hidden system skills stay available but require explicit activation."""
        monkeypatch.setattr(
            "siada.services.skills.renderer.HIDDEN_SYSTEM_SKILLS",
            frozenset({"hidden-system-skill"}),
        )
        skills = [
            SkillMetadata(
                "hidden-system-skill",
                "Hidden system instructions",
                Path("/system/hidden-system-skill/SKILL.md"),
                SkillScope.SYSTEM,
            ),
            SkillMetadata(
                "visible-skill",
                "Visible instructions",
                Path("/user/visible-skill/SKILL.md"),
                SkillScope.USER,
            ),
        ]

        without_activation = render_skills_section(skills)
        assert without_activation is not None
        assert "hidden-system-skill" not in without_activation
        assert "visible-skill" in without_activation

        with_activation = render_skills_section(
            skills, activated_skill_names={"hidden-system-skill"}
        )
        assert with_activation is not None
        assert "hidden-system-skill" in with_activation

    def test_default_hidden_skills_and_long_horizon_expansion(self):
        """Long-horizon exposes the hidden workflow skills except design-doc-writer."""
        hidden_names = {
            "finishing-a-development-branch",
            "receiving-code-review",
            "test-driven-development",
            "long-horizon",
            "brainstorming",
            "verification-before-completion",
            "systematic-debugging",
            "dispatching-parallel-agents",
            "executing-plans",
            "requesting-code-review",
            "subagent-driven-development",
            "design-doc-writer",
            "writing-plans",
        }
        skills = [
            SkillMetadata(
                name,
                f"{name} instructions",
                Path(f"/system/{name}/SKILL.md"),
                SkillScope.SYSTEM,
            )
            for name in hidden_names
        ]

        assert render_skills_section(skills) is None

        rendered = render_skills_section(
            skills, activated_skill_names={"long-horizon"}
        )
        assert rendered is not None
        for name in hidden_names - {"design-doc-writer"}:
            assert name in rendered
        assert "design-doc-writer" not in rendered



    
    def test_render_skill_summary(self):
        """Test skill summary rendering"""
        skills = [
            SkillMetadata("skill-1", "desc", Path("/1"), SkillScope.REPO),
            SkillMetadata("skill-2", "desc", Path("/2"), SkillScope.USER),
        ]
        
        summary = render_skill_summary(skills)
        
        assert "2 skill(s)" in summary
        assert "skill-1" in summary
        assert "skill-2" in summary
    
    def test_render_skill_summary_empty(self):
        """Test summary with no skills"""
        summary = render_skill_summary([])
        assert "No skills loaded" in summary

    @staticmethod
    def _norm(text: str) -> str:
        """Normalize path separators for cross-platform assertions"""
        return text.replace("\\", "/")

    def test_render_skills_section_with_skill_roots_aliased(self):
        """Skills under a shared root render short aliased paths + roots table"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir).resolve()
            user_root = base / "user" / "skills"
            repo_root = base / "repo" / "skills"
            skills = [
                SkillMetadata(
                    name="beta",
                    description="Repo skill",
                    path=repo_root / "beta" / "SKILL.md",
                    scope=SkillScope.REPO,
                ),
                SkillMetadata(
                    name="alpha",
                    description="User skill",
                    path=user_root / "alpha" / "SKILL.md",
                    scope=SkillScope.USER,
                ),
            ]
            # REPO inserted first on purpose: alias order must follow scope
            # priority (USER=0), not dict insertion order
            roots = {SkillScope.REPO: [repo_root], SkillScope.USER: [user_root]}

            result = render_skills_section(skills, skill_roots=roots)

            assert result is not None
            assert "### Skill roots" in result
            norm = self._norm(result)
            assert self._norm(f"- `r0` = `{user_root}`") in norm
            assert self._norm(f"- `r1` = `{repo_root}`") in norm
            # Entries sorted by name and rendered with aliased short paths
            assert "- alpha: User skill (file: r0/alpha/SKILL.md)" in result
            assert "- beta: Repo skill (file: r1/beta/SKILL.md)" in result
            assert result.index("alpha") < result.index("beta")
            # The shared catalog intro explains the alias-to-root mapping;
            # strict usage rules then give their profile-specific procedure.
            assert "maps aliases such as `r0` to their absolute filesystem roots" in result
            assert "Expand the matching alias before accessing the skill." in result
            assert "expanding the matching alias from `### Skill roots`" in result

    def test_render_skills_section_deterministic_across_input_order(self):
        """Same skill set renders byte-identical output regardless of input order"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir).resolve()
            root = base / "skills"
            skills = [
                SkillMetadata("gamma", "G", root / "gamma" / "SKILL.md", SkillScope.USER),
                SkillMetadata("alpha", "A", root / "alpha" / "SKILL.md", SkillScope.USER),
                SkillMetadata("beta", "B", root / "beta" / "SKILL.md", SkillScope.USER),
            ]
            roots = {SkillScope.USER: [root]}

            first = render_skills_section(skills, skill_roots=roots)
            shuffled = render_skills_section(list(reversed(skills)), skill_roots=roots)
            repeat = render_skills_section(skills, skill_roots=roots)

            assert first == shuffled == repeat

    def test_render_skills_section_unmatched_skill_keeps_absolute(self):
        """Skills outside all configured roots fall back to absolute paths"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir).resolve()
            root = base / "skills"
            outside_path = base / "elsewhere" / "solo" / "SKILL.md"
            skills = [
                SkillMetadata("inside", "In", root / "inside" / "SKILL.md", SkillScope.USER),
                SkillMetadata("outside", "Out", outside_path, SkillScope.USER),
            ]

            result = render_skills_section(skills, skill_roots={SkillScope.USER: [root]})

            assert result is not None
            assert "- inside: In (file: r0/inside/SKILL.md)" in result
            assert self._norm(f"- outside: Out (file: {outside_path})") in self._norm(result)

    def test_render_skills_section_without_roots_uses_absolute(self):
        """Without skill_roots, entries render absolute paths and no roots table"""
        skills = [
            SkillMetadata("skill-a", "Description A", Path("/path/a/SKILL.md"), SkillScope.REPO),
        ]

        result = render_skills_section(skills)

        assert result is not None
        assert "### Skill roots" not in result
        assert "- skill-a: Description A (file: /path/a/SKILL.md)" in result

    def test_render_skills_section_how_to_use_rules(self):
        """How-to-use rules require complete reads and forbid subagent delegation"""
        skills = [
            SkillMetadata("skill-a", "desc", Path("/path/a/SKILL.md"), SkillScope.REPO),
        ]

        result = render_skills_section(skills)

        assert result is not None
        assert "read its `SKILL.md` at the listed path completely before taking task actions" in result
        assert "Do not delegate reading, summarizing, or interpreting skill instructions to a subagent" in result
        assert "not partially reading a selected instruction file" in result

    def test_strict_profile_preserves_existing_rendering(self):
        """STRICT is the default, preserving current model prompt bytes."""
        skills = [
            SkillMetadata("skill-a", "desc", Path("/path/a/SKILL.md"), SkillScope.REPO),
        ]

        implicit = render_skills_section(skills)
        explicit = render_skills_section(skills, usage_profile=SkillUsageProfile.STRICT)

        assert implicit == explicit
        assert "you must use that skill for that turn" in explicit
        assert "completely before taking task actions" in explicit

    def test_gpt6_profile_uses_judgement_and_approval_guardrails(self):
        skills = [
            SkillMetadata("skill-a", "desc", Path("/path/a/SKILL.md"), SkillScope.REPO),
        ]

        result = render_skills_section(skills, usage_profile=SkillUsageProfile.GPT6)

        assert result is not None
        assert "reasonable judgement" in result
        assert "prioritize the user's instructions" in result
        assert "explicitly require approval" in result
        assert "long-horizon" not in result
        assert "only hidden" not in result
        assert "slash command" not in result
        assert "you must use that skill" not in result
        assert "completely before taking task actions" not in result
        assert "Do not delegate" not in result
        assert "skills.list" not in result
        assert "skills.read" not in result
        assert "environment-owned" not in result
        assert "skill://" not in result
        assert "commentary channel" not in result

    def test_gpt6_profile_expands_aliased_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "skills"
            skills = [
                SkillMetadata("skill-a", "desc", root / "skill-a" / "SKILL.md", SkillScope.USER),
            ]

            result = render_skills_section(
                skills,
                skill_roots={SkillScope.USER: [root]},
                usage_profile=SkillUsageProfile.GPT6,
            )

        assert result is not None
        assert "maps aliases such as `r0` to their absolute filesystem roots" in result
        assert "Expand the matching alias before accessing the skill." in result
        assert "Expand a short path" in result
        assert "r0/skill-a/SKILL.md" in result

    def test_gpt6_profile_without_roots_never_mentions_aliases(self):
        """The absolute-path layout renders no `### Skill roots` table, so the
        how-to text must not tell the model to expand an alias."""
        skills = [
            SkillMetadata("skill-a", "desc", Path("/path/a/SKILL.md"), SkillScope.REPO),
        ]

        result = render_skills_section(skills, usage_profile=SkillUsageProfile.GPT6)

        assert result is not None
        assert "### Skill roots" not in result
        assert "alias" not in result.lower()
        assert "Open that path to read" in result

    def test_gpt6_profile_is_deterministic(self):
        skills = [
            SkillMetadata("skill-a", "desc", Path("/path/a/SKILL.md"), SkillScope.REPO),
        ]

        first = render_skills_section(skills, usage_profile=SkillUsageProfile.GPT6)
        second = render_skills_section(skills, usage_profile=SkillUsageProfile.GPT6)

        assert first == second


# ============================================================================
# Integration Tests
# ============================================================================

class TestRendererDescriptionBudget:
    """Test skill-list description display cap and total budget degradation
    (mechanism borrowed from codex-rs/ext/skills/src/render.rs)"""

    @staticmethod
    def _make_skills(count: int, desc_len: int) -> list:
        return [
            SkillMetadata(
                name=f"skill-{i:03d}",
                description=f"d{i}-" + "x" * desc_len,
                path=Path(f"/path/{i:03d}/SKILL.md"),
                scope=SkillScope.REPO,
            )
            for i in range(count)
        ]

    def test_single_description_display_cap_1024(self):
        """One description is clipped at 1024 chars (aligned with parse limit)"""
        skills = [
            SkillMetadata("s", "a" * 1500, Path("/p/SKILL.md"), SkillScope.REPO)
        ]
        result = render_skills_section(skills)
        line = next(l for l in result.splitlines() if l.startswith("- s:"))
        shown = line[len("- s: "):line.index(" (file:")]
        assert len(shown) == 1024
        assert shown.endswith("...")

    def test_budget_fits_full_descriptions(self):
        """Small list fits the 8000-char fallback budget without clipping"""
        skills = self._make_skills(3, 100)
        result = render_skills_section(skills)
        assert "..." not in result
        for i in range(3):
            assert f"d{i}-" + "x" * 100 in result

    def test_budget_shortens_long_descriptions(self):
        """10 x ~1027-char descriptions exceed 8000 chars: uniform clipping,
        every skill still listed"""
        skills = self._make_skills(10, 1024)
        result = render_skills_section(skills)
        assert "..." in result
        for i in range(10):
            assert f"skill-{i:03d}" in result
        # no description survives in full
        assert "x" * 1024 not in result

    def test_budget_shortens_logs_warning(self):
        from unittest.mock import patch

        skills = self._make_skills(10, 1024)
        with patch("siada.services.skills.renderer.logger") as mock_logger:
            render_skills_section(skills)
        assert mock_logger.warning.called
        assert "shortened" in mock_logger.warning.call_args[0][0]

    def test_budget_removes_descriptions_when_tight(self):
        """context_window=2000 -> 2% = 40 tokens -> 160 chars budget: only
        name+path lines fit, descriptions fully removed"""
        skills = self._make_skills(4, 200)
        result = render_skills_section(skills, context_window=2000)
        for i in range(4):
            assert f"skill-{i:03d}" in result  # every skill still listed
            assert f"d{i}-" not in result  # descriptions removed
        assert ": (file:" in result

    def test_budget_omits_trailing_skills(self):
        """context_window=500 -> 10 tokens -> 40 chars budget: even name+path
        lines overflow, trailing entries omitted with a trailer"""
        skills = self._make_skills(10, 50)
        result = render_skills_section(skills, context_window=500)
        assert "(+" in result
        assert "more skills)" in result

    def test_large_context_window_raises_budget(self):
        """1M window -> 20k tokens -> 80k chars: everything fits unclipped
        (descriptions kept under the 1024 single-entry display cap)"""
        skills = self._make_skills(10, 1000)
        result = render_skills_section(skills, context_window=1_000_000)
        assert "..." not in result

    def test_manager_forwards_context_window(self):
        """SkillsManager.get_skills_section forwards context_window to the renderer"""
        from unittest.mock import patch

        SkillsManager.reset_instance()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                manager = SkillsManager(Path(tmpdir) / "home")
                cwd = Path(tmpdir) / "proj"
                cwd.mkdir()
                with patch(
                    "siada.services.skills.manager.render_skills_section"
                ) as mock_render:
                    mock_render.return_value = None
                    manager.get_skills_section(cwd, context_window=123_456)
                assert mock_render.call_args.kwargs["context_window"] == 123_456
        finally:
            SkillsManager.reset_instance()

    def test_manager_forwards_usage_profile(self):
        """SkillsManager.get_skills_section forwards the selected profile."""
        from unittest.mock import patch

        SkillsManager.reset_instance()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                manager = SkillsManager(Path(tmpdir) / "home")
                cwd = Path(tmpdir) / "proj"
                cwd.mkdir()
                with patch(
                    "siada.services.skills.manager.render_skills_section"
                ) as mock_render:
                    mock_render.return_value = None
                    manager.get_skills_section(cwd, usage_profile=SkillUsageProfile.GPT6)
                assert mock_render.call_args.kwargs["usage_profile"] is SkillUsageProfile.GPT6
        finally:
            SkillsManager.reset_instance()

    def test_skills_context_window_resolution(self):
        """code_gen_prompt resolves the base context window from model_name"""
        from siada.agent_hub.coder.prompt.code_gen_prompt import _skills_context_window
        from siada.models.model_base_config import MODEL_SETTING

        assert _skills_context_window(None) is None
        assert _skills_context_window("") is None
        assert _skills_context_window("no-such-model-xyz") is None

        first = MODEL_SETTING[0]
        assert _skills_context_window(first.model_name) == first.context_window


class TestIntegration:
    """Integration tests"""
    
    def setup_method(self):
        """Reset singleton before each test"""
        SkillsManager.reset_instance()
    
    def teardown_method(self):
        """Reset singleton after each test"""
        SkillsManager.reset_instance()
    
    def test_end_to_end(self):
        """Test complete workflow"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Setup directories
            project_root = tmppath / "project"
            project_root.mkdir()
            
            repo_skills = project_root / ".siada" / "skills"
            skill_dir = repo_skills / "my-tool"
            skill_dir.mkdir(parents=True)
            (skill_dir / SKILL_FILENAME).write_text("""---
name: my-tool
description: A custom tool for my project
metadata:
  short-description: Custom tool
---

# My Tool

Instructions here.
""")
            
            siada_home = tmppath / ".siada-cli"
            siada_home.mkdir()
            
            # Load skills
            manager = SkillsManager(siada_home)
            outcome = manager.skills_for_cwd(project_root)
            
            # Verify loading
            assert len(outcome.skills) >= 1
            my_tool = manager.get_skill_by_name(project_root, "my-tool")
            assert my_tool is not None
            assert my_tool.description == "A custom tool for my project"
            
            # Render section
            section = render_skills_section(outcome.skills)
            assert section is not None
            assert "my-tool" in section


# ============================================================================
# System Skill Tests
# ============================================================================

class TestSystemSkills:
    """Test built-in system skills"""
    
    def setup_method(self):
        """Reset singleton before each test"""
        SkillsManager.reset_instance()
    
    def teardown_method(self):
        """Reset singleton after each test"""
        SkillsManager.reset_instance()
    
    def test_skill_creator_exists(self):
        """Test that skill-creator is available as system skill"""
        from siada.services.skills.config import get_system_skills_root
        
        system_root = get_system_skills_root()
        skill_creator = system_root / "skill-creator" / SKILL_FILENAME
        
        assert skill_creator.exists(), f"skill-creator not found at {skill_creator}"
    
    def test_skill_creator_parseable(self):
        """Test that skill-creator can be parsed"""
        from siada.services.skills.config import get_system_skills_root
        
        system_root = get_system_skills_root()
        skill_dir = system_root / "skill-creator"
        
        skill = parse_skill_file(skill_dir, SkillScope.SYSTEM)
        
        assert skill.name == "skill-creator"
        assert "skill" in skill.description.lower()
