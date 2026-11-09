"""Regression tests for conf_store round-trip updates.

Guards the incident where a conf.yaml containing duplicate keys (e.g. an old
`checkpoint_config:` section appended twice, both values None) made every
update_conf() write fail with ruamel's DuplicateKeyError, so switching models
via ACP raised "Failed to save selected model to conf.yaml".
"""

from siada.config.conf_store import read_conf_dict, save_conf_fields, update_conf


DUPLICATE_CONF = """\
# Siada config
llm_config:
  model: old-model  # keep this comment
checkpoint_config:
checkpoint_config:

proactive:
  enabled: false
"""


def _read(path):
    return path.read_text(encoding="utf-8")


class TestUpdateConfDuplicateKeys:
    def test_save_succeeds_and_removes_duplicates(self, tmp_path):
        conf = tmp_path / "conf.yaml"
        conf.write_text(DUPLICATE_CONF, encoding="utf-8")

        assert save_conf_fields({"llm_config.model": "gpt-6.1-sol"}, conf) is True

        content = _read(conf)
        assert content.count("checkpoint_config:") == 1
        assert "model: gpt-6.1-sol" in content
        # Comments outside the duplicated section survive the rewrite.
        assert "# keep this comment" in content

    def test_last_occurrence_wins(self, tmp_path):
        """Healed values follow the read path (PyYAML): last occurrence wins."""
        conf = tmp_path / "conf.yaml"
        conf.write_text(
            "checkpoint_config:\n  enable: false\ncheckpoint_config:\n  enable: true\n",
            encoding="utf-8",
        )

        assert save_conf_fields({"proactive.enabled": True}, conf) is True

        assert read_conf_dict(conf)["checkpoint_config"] == {"enable": True}

    def test_nested_duplicate_keys_healed(self, tmp_path):
        conf = tmp_path / "conf.yaml"
        conf.write_text(
            "checkpoint_config:\n  enable: false\n  enable: true\n",
            encoding="utf-8",
        )

        assert save_conf_fields({"llm_config.model": "m"}, conf) is True

        content = _read(conf)
        assert content.count("enable:") == 1
        assert read_conf_dict(conf)["checkpoint_config"]["enable"] is True

    def test_healed_file_needs_no_recovery_on_next_save(self, tmp_path):
        conf = tmp_path / "conf.yaml"
        conf.write_text(DUPLICATE_CONF, encoding="utf-8")
        assert save_conf_fields({"llm_config.model": "m1"}, conf) is True

        # Second save on the healed file must succeed under strict loading.
        assert save_conf_fields({"llm_config.model": "m2"}, conf) is True
        assert read_conf_dict(conf)["llm_config"]["model"] == "m2"

    def test_mutator_false_aborts_write_and_leaves_file_unchanged(self, tmp_path):
        conf = tmp_path / "conf.yaml"
        conf.write_text(DUPLICATE_CONF, encoding="utf-8")
        original = _read(conf)

        assert update_conf(lambda data: False, conf) is True
        assert _read(conf) == original

    def test_real_syntax_error_still_fails(self, tmp_path):
        conf = tmp_path / "conf.yaml"
        conf.write_text("llm_config:\n  model: [unclosed\n", encoding="utf-8")

        assert save_conf_fields({"llm_config.model": "m"}, conf) is False

    def test_comments_preserved_on_clean_file(self, tmp_path):
        conf = tmp_path / "conf.yaml"
        conf.write_text(
            "# top\nllm_config:\n  model: old  # inline\n", encoding="utf-8"
        )

        assert save_conf_fields({"llm_config.model": "new"}, conf) is True

        content = _read(conf)
        assert "# top" in content
        assert "# inline" in content
        assert read_conf_dict(conf)["llm_config"]["model"] == "new"
