"""
Tests for _ensure_config_up_to_date in config_loader.py
"""
import tempfile
from pathlib import Path

import pytest

from siada.config.config_loader import (
    SubAgentConfig,
    _ensure_config_up_to_date,
    _backup_config_file,
    _DEFAULT_CONFIG_TEMPLATE,
)


class TestEnsureConfigUpToDate:

    def _write(self, path: Path, content: str) -> None:
        path.write_text(content, encoding='utf-8')

    def _read(self, path: Path) -> str:
        return path.read_text(encoding='utf-8')

    def test_no_op_when_all_keys_present(self, tmp_path):
        """File already contains every template key — should not be modified."""
        config_file = tmp_path / 'conf.yaml'
        self._write(config_file, _DEFAULT_CONFIG_TEMPLATE)
        original = self._read(config_file)

        _ensure_config_up_to_date(config_file)

        assert self._read(config_file) == original

    def test_appends_missing_active_section(self, tmp_path):
        """A new active section absent from the existing file is appended."""
        config_file = tmp_path / 'conf.yaml'
        # Start with a minimal file that has no `memory` key at all
        self._write(config_file, "llm_config:\n  model: claude\n")

        _ensure_config_up_to_date(config_file)

        content = self._read(config_file)
        # The memory section from the template must now be present
        assert 'memory' in content

    def test_appends_missing_commented_section(self, tmp_path):
        """A new commented section absent from the existing file is appended."""
        config_file = tmp_path / 'conf.yaml'
        # File has no `lark` key whatsoever
        self._write(config_file, "proactive:\n  enabled: true\n")

        _ensure_config_up_to_date(config_file)

        content = self._read(config_file)
        assert 'lark' in content

    def test_does_not_duplicate_commented_key(self, tmp_path):
        """If the file already has `# key:` (commented form), the section is NOT added again."""
        config_file = tmp_path / 'conf.yaml'
        # User has memory commented out
        self._write(config_file, "llm_config:\n  model: claude\n\n# memory:\n#   enabled: true\n")

        _ensure_config_up_to_date(config_file)

        content = self._read(config_file)
        # Should appear exactly once
        assert content.count('memory') == content.count('memory')  # sanity
        assert content.count('# memory:') == 1

    def test_does_not_duplicate_active_key(self, tmp_path):
        """If the file already has an active `key:`, the section is NOT added again."""
        config_file = tmp_path / 'conf.yaml'
        self._write(config_file, "memory:\n  enabled: false\n")

        _ensure_config_up_to_date(config_file)

        content = self._read(config_file)
        assert content.count('memory:') == 1

    def test_preserves_existing_content(self, tmp_path):
        """Existing file content is never modified — only appended to."""
        config_file = tmp_path / 'conf.yaml'
        original = "llm_config:\n  api_key: secret\n"
        self._write(config_file, original)

        _ensure_config_up_to_date(config_file)

        content = self._read(config_file)
        assert content.startswith(original)

    def test_idempotent(self, tmp_path):
        """Calling the function multiple times produces the same result."""
        config_file = tmp_path / 'conf.yaml'
        self._write(config_file, "llm_config:\n  model: claude\n")

        _ensure_config_up_to_date(config_file)
        after_first = self._read(config_file)

        _ensure_config_up_to_date(config_file)
        after_second = self._read(config_file)

        assert after_first == after_second

    def test_missing_multiple_sections(self, tmp_path):
        """Multiple missing sections are all appended in a single pass."""
        config_file = tmp_path / 'conf.yaml'
        # Only proactive is present; memory, lark, auto_update are absent
        self._write(config_file, "proactive:\n  enabled: true\n")

        _ensure_config_up_to_date(config_file)

        content = self._read(config_file)
        assert 'memory' in content
        assert 'lark' in content
        assert 'auto_update' in content

    def test_graceful_on_unreadable_file(self, tmp_path):
        """If the file cannot be read, the function exits silently without raising."""
        non_existent = tmp_path / 'ghost.yaml'
        # Should not raise even though the file does not exist
        _ensure_config_up_to_date(non_existent)

    def test_backup_created_when_sections_appended(self, tmp_path):
        """A backup file is created before the config is modified."""
        config_file = tmp_path / 'conf.yaml'
        self._write(config_file, "llm_config:\n  model: claude\n")

        _ensure_config_up_to_date(config_file)

        backups = list(tmp_path.glob('conf-*.yaml'))
        assert len(backups) == 1

    def test_no_backup_when_nothing_missing(self, tmp_path):
        """No backup is created when the file is already up to date."""
        config_file = tmp_path / 'conf.yaml'
        self._write(config_file, _DEFAULT_CONFIG_TEMPLATE)

        _ensure_config_up_to_date(config_file)

        backups = list(tmp_path.glob('conf-*.yaml'))
        assert len(backups) == 0

    def test_backup_content_matches_original(self, tmp_path):
        """The backup is an exact copy of the file before modification."""
        config_file = tmp_path / 'conf.yaml'
        original = "llm_config:\n  model: claude\n"
        self._write(config_file, original)

        _ensure_config_up_to_date(config_file)

        backup = list(tmp_path.glob('conf-*.yaml'))[0]
        assert backup.read_text(encoding='utf-8') == original


class TestBackupConfigFile:

    def _write(self, path: Path, content: str) -> None:
        path.write_text(content, encoding='utf-8')

    def test_backup_filename_format(self, tmp_path):
        """Backup filename contains a YYYYMMDD-HHmmss timestamp."""
        import re
        config_file = tmp_path / 'conf.yaml'
        self._write(config_file, 'key: value\n')

        _backup_config_file(config_file)

        backups = list(tmp_path.glob('conf-*.yaml'))
        assert len(backups) == 1
        assert re.match(r'conf-\d{8}-\d{6}\.yaml', backups[0].name)

    def test_max_backups_enforced(self, tmp_path):
        """Only the most recent max_backups files are kept."""
        import time
        config_file = tmp_path / 'conf.yaml'
        self._write(config_file, 'key: value\n')

        # Pre-create 11 backup files with distinct timestamps (1s apart via name)
        for i in range(11):
            backup = tmp_path / f'conf-2025010{i // 10}-10000{i}.yaml'
            backup.write_text('old backup', encoding='utf-8')
            time.sleep(0.01)  # ensure distinct mtime ordering

        # One more backup call should prune down to 10
        _backup_config_file(config_file, max_backups=10)

        backups = list(tmp_path.glob('conf-*.yaml'))
        assert len(backups) == 10

    def test_oldest_backups_removed(self, tmp_path):
        """When over the limit, the oldest (by mtime) backups are removed."""
        import time
        config_file = tmp_path / 'conf.yaml'
        self._write(config_file, 'key: value\n')

        # Pre-create 4 old backups with distinct mtimes
        old_backups = []
        for i in range(4):
            b = tmp_path / f'conf-20250101-10000{i}.yaml'
            b.write_text('old', encoding='utf-8')
            old_backups.append(b)
            time.sleep(0.01)

        # Trigger backup with limit=3; the 4 old ones + 1 new = 5 total → prune to 3
        _backup_config_file(config_file, max_backups=3)

        remaining = sorted(tmp_path.glob('conf-*.yaml'), key=lambda p: p.name)
        assert len(remaining) == 3
        # The 2 oldest pre-created backups should be gone
        assert not old_backups[0].exists()
        assert not old_backups[1].exists()

    def test_graceful_on_missing_source(self, tmp_path):
        """Does not raise if the source file does not exist."""
        _backup_config_file(tmp_path / 'nonexistent.yaml')


class TestSubAgentTemplateSectionStability:
    """Regression guard: the sub_agent template paragraph's prose must not
    contain any stray ``word:`` pattern that ``_ensure_config_up_to_date``'s
    key detector would mistake for a second top-level key -- that bug caused
    the whole paragraph (including the real ``sub_agent:`` key) to be
    appended twice on every load when the file already had one of the
    "keys" from that false match but not the real ones."""

    def _write(self, path: Path, content: str) -> None:
        path.write_text(content, encoding='utf-8')

    def _read(self, path: Path) -> str:
        return path.read_text(encoding='utf-8')

    def test_sub_agent_paragraph_has_exactly_one_top_level_key(self):
        import re
        top_key_re = re.compile(r'^(?:# )?([a-z][a-z0-9_]*):', re.MULTILINE)
        paragraphs = re.split(r'\n{2,}', _DEFAULT_CONFIG_TEMPLATE.strip())
        sub_agent_paragraphs = [
            p for p in paragraphs if 'sub_agent' in top_key_re.findall(p)
        ]
        assert len(sub_agent_paragraphs) == 1
        keys = top_key_re.findall(sub_agent_paragraphs[0])
        assert keys == ['sub_agent']

    def test_repeated_loads_do_not_duplicate_sub_agent_section(self, tmp_path):
        config_file = tmp_path / 'conf.yaml'
        self._write(config_file, "llm_config:\n  model: claude\n")

        _ensure_config_up_to_date(config_file)
        _ensure_config_up_to_date(config_file)
        _ensure_config_up_to_date(config_file)

        content = self._read(config_file)
        assert content.count('Sub-Agent Configuration (run_subtask)') == 1
        assert content.count('# sub_agent:') == 1


class TestSubAgentConfigFromDict:
    def test_defaults_to_false(self):
        cfg = SubAgentConfig.from_dict({})
        assert cfg.allow_recursive_subagents is False

    def test_reads_true(self):
        cfg = SubAgentConfig.from_dict({"allow_recursive_subagents": True})
        assert cfg.allow_recursive_subagents is True

    def test_reads_explicit_false(self):
        cfg = SubAgentConfig.from_dict({"allow_recursive_subagents": False})
        assert cfg.allow_recursive_subagents is False

    def test_none_value_falls_back_to_default(self):
        cfg = SubAgentConfig.from_dict({"allow_recursive_subagents": None})
        assert cfg.allow_recursive_subagents is False

    def test_master_switch_defaults_to_true(self):
        cfg = SubAgentConfig.from_dict({})
        assert cfg.enabled is True

    def test_master_switch_reads_explicit_false(self):
        cfg = SubAgentConfig.from_dict({"enabled": False})
        assert cfg.enabled is False

    def test_master_switch_none_value_falls_back_to_true(self):
        cfg = SubAgentConfig.from_dict({"enabled": None})
        assert cfg.enabled is True

    def test_master_switch_off_forces_recursion_off(self):
        """Recursive nesting is an extension of the feature it must not outlive."""
        cfg = SubAgentConfig.from_dict(
            {"enabled": False, "allow_recursive_subagents": True}
        )
        assert cfg.enabled is False
        assert cfg.allow_recursive_subagents is False

    def test_master_switch_on_keeps_recursion_flag(self):
        cfg = SubAgentConfig.from_dict(
            {"enabled": True, "allow_recursive_subagents": True}
        )
        assert cfg.enabled is True
        assert cfg.allow_recursive_subagents is True


class TestSubAgentTemplateMasterSwitch:
    def test_template_example_documents_enabled(self):
        import re
        paragraphs = re.split(r'\n{2,}', _DEFAULT_CONFIG_TEMPLATE.strip())
        sub_agent_paragraph = next(p for p in paragraphs if '# sub_agent:' in p)
        assert '#   enabled: true' in sub_agent_paragraph
        assert '#   allow_recursive_subagents: false' in sub_agent_paragraph
