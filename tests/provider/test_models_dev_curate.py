"""Curated provider/model list for the login UI (models.dev)."""

from siada.provider import models_dev


def _model(name, release_date, *, tool_call=True, experimental=None, context=128_000):
    entry = {
        "name": name,
        "tool_call": tool_call,
        "release_date": release_date,
        "limit": {"context": context},
    }
    if experimental is not None:
        entry["experimental"] = experimental
    return entry


def test_curate_keeps_released_models_with_experimental_mode_descriptor():
    """models.dev's `experimental` is an object (feature modes / per-mode
    pricing) for the newest released models, not a boolean flag. Such models
    must NOT be filtered out just because the object is truthy."""
    raw = {
        "openai": {
            "models": {
                "gpt-6.1-sol": _model(
                    "GPT-6.1 Sol",
                    "2026-09-29",
                    experimental={"modes": {"fast": {}, "pro": {}, "ultrafast": {}}},
                    context=1_000_000,
                ),
                "gpt-old": _model("GPT Old", "2026-01-01"),
            }
        }
    }

    providers = {p["id"]: p for p in models_dev._curate(raw)}
    models = providers["openai"]["models"]
    ids = [m["id"] for m in models]

    assert ids[0] == "gpt-6.1-sol"  # newest first, kept despite the dict
    assert models[0]["context"] == 1_000  # 1_000_000 // 1000
    assert "gpt-old" in ids


def test_curate_drops_only_explicitly_experimental_and_non_tool_models():
    raw = {
        "openai": {
            "models": {
                "gpt-truly-experimental": _model(
                    "Truly Experimental", "2026-09-30", experimental=True
                ),
                "gpt-no-tools": _model("No tools", "2026-09-30", tool_call=False),
                "gpt-deprecated": {
                    "name": "Deprecated",
                    "tool_call": True,
                    "status": "deprecated",
                    "release_date": "2026-09-30",
                    "limit": {"context": 128_000},
                },
                "gpt-kept": _model("Kept", "2026-09-29"),
            }
        }
    }

    providers = {p["id"]: p for p in models_dev._curate(raw)}
    ids = [m["id"] for m in providers["openai"]["models"]]

    assert ids == ["gpt-kept"]


def test_curate_caps_models_per_provider_and_appends_custom():
    models = {
        f"gpt-{i:02d}": _model(f"GPT {i}", f"2026-01-{i:02d}")
        for i in range(1, 13)
    }
    providers = models_dev._curate({"openai": {"models": models}})

    openai = next(p for p in providers if p["id"] == "openai")
    assert len(openai["models"]) == 8
    assert providers[-1]["id"] == "custom"
    assert providers[-1]["models"] == []