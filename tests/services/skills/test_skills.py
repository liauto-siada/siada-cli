"""
Tests for siada/services/skills module
"""

import tempfile
import pytest
from pathlib import Path

from siada.services.skills import (
    SkillScope,
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


# ============================================================================
# Integration Tests
# ============================================================================

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
