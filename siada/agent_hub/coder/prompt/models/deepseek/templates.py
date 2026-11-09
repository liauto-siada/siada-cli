from functools import lru_cache
from pathlib import Path


_TEMPLATES_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=6)
def _load_template(name: str) -> str:
    return (_TEMPLATES_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def get_deepseek_template() -> str:
    return _load_template("system")


def get_deepseek_skills_guidance() -> str:
    return _load_template("skills")


def get_deepseek_delegation_guidance() -> str:
    return _load_template("delegation")


def get_deepseek_web_search_guidance(fetch_enabled: bool) -> str:
    return _load_template("web-search" if fetch_enabled else "web-search-only")


def get_deepseek_web_fetch_guidance() -> str:
    return _load_template("web-fetch")
