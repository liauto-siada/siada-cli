import json
import pytest
from unittest.mock import patch
from pathlib import Path

from siada.services.plugins.marketplace_manager import MarketplaceManager


class TestMarketplaceManagerConfig:
    def test_get_config_default_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path
        )
        manager = MarketplaceManager()
        config = manager.get_config()
        assert "marketplaces" in config
        assert "disabled_skills" in config

    def test_save_and_reload_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path
        )
        manager = MarketplaceManager()
        config = {"marketplaces": [{"name": "test", "repo": "owner/repo"}], "disabled_skills": []}
        manager.save_config(config)
        loaded = manager.get_config()
        # test marketplace preserved (default marketplace may also be prepended)
        names = [m["name"] for m in loaded["marketplaces"]]
        assert "test" in names

    def test_add_marketplace(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path
        )
        manager = MarketplaceManager()
        manager.add_marketplace("owner/new-repo")
        config = manager.get_config()
        names = [m["name"] for m in config["marketplaces"]]
        assert "new-repo" in names

    def test_add_duplicate_marketplace_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path
        )
        manager = MarketplaceManager()
        manager.add_marketplace("owner/my-repo")
        with pytest.raises(ValueError, match="already configured"):
            manager.add_marketplace("owner/my-repo")

    def test_remove_marketplace(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path
        )
        manager = MarketplaceManager()
        manager.add_marketplace("owner/to-remove")
        manager.remove_marketplace("to-remove")
        config = manager.get_config()
        names = [m["name"] for m in config["marketplaces"]]
        assert "to-remove" not in names

    def test_remove_nonexistent_marketplace_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path
        )
        manager = MarketplaceManager()
        with pytest.raises(ValueError, match="not found"):
            manager.remove_marketplace("ghost-that-does-not-exist-xyz")


class TestFetchMarketplaceSkills:
    def test_fetch_github_marketplace_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path
        )
        marketplace_payload = json.dumps({
            "plugins": [
                {"name": "skill-a", "description": "Skill A"},
                {"name": "skill-b", "description": "Skill B"},
            ]
        }).encode()

        def mock_fetch(url, headers=None, timeout=8):
            if ".claude-plugin/marketplace.json" in url:
                return marketplace_payload
            return None

        manager = MarketplaceManager()
        with patch.object(manager, "_fetch_url", side_effect=mock_fetch):
            mp = {"name": "test", "repo": "https://github.com/owner/repo.git"}
            skills = manager.fetch_skills(mp)

        assert len(skills) == 2
        assert skills[0]["name"] == "skill-a"

    def test_fetch_returns_empty_on_network_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path
        )
        manager = MarketplaceManager()
        with patch.object(manager, "_fetch_url", return_value=None):
            mp = {"name": "test", "repo": "https://github.com/owner/repo.git"}
            skills = manager.fetch_skills(mp)
        assert skills == []
