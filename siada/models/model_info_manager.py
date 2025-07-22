import difflib
import hashlib
import importlib.resources
import json
import math
import os
import platform
import sys
import time
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import json5
import yaml
from PIL import Image

from aider import __version__
from aider.dump import dump  # noqa: F401
from aider.llm import litellm
from aider.openrouter import OpenRouterModelManager
from aider.sendchat import ensure_alternating_roles, sanity_check_messages
from aider.utils import check_pip_install_extra


class ModelInfoManager:
    MODEL_INFO_URL = (
        "https://raw.githubusercontent.com/BerriAI/litellm/main/"
        "model_prices_and_context_window.json"
    )
    CACHE_TTL = 60 * 60 * 24  # 24 hours

    def __init__(self):
        self.cache_dir = Path.home() / ".siada-cli" / "caches"
        self.cache_file = self.cache_dir / "model_prices_and_context_window.json"
        self.content = None
        self.local_model_metadata = {}
        self.verify_ssl = True
        self._cache_loaded = False

        # Manager for the cached OpenRouter model database
        self.openrouter_manager = OpenRouterModelManager()

    def set_verify_ssl(self, verify_ssl):
        self.verify_ssl = verify_ssl
        if hasattr(self, "openrouter_manager"):
            self.openrouter_manager.set_verify_ssl(verify_ssl)

    def _load_cache(self):
        if self._cache_loaded:
            return

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            if self.cache_file.exists():
                cache_age = time.time() - self.cache_file.stat().st_mtime
                if cache_age < self.CACHE_TTL:
                    try:
                        self.content = json.loads(self.cache_file.read_text())
                    except json.JSONDecodeError:
                        # If the cache file is corrupted, treat it as missing
                        self.content = None
        except OSError:
            pass

        self._cache_loaded = True

    def _update_cache(self):
        try:
            import requests

            # Respect the --no-verify-ssl switch
            response = requests.get(self.MODEL_INFO_URL, timeout=5, verify=self.verify_ssl)
            if response.status_code == 200:
                self.content = response.json()
                try:
                    self.cache_file.write_text(json.dumps(self.content, indent=4))
                except OSError:
                    pass
        except Exception as ex:
            print(str(ex))
            try:
                # Save empty dict to cache file on failure
                self.cache_file.write_text("{}")
            except OSError:
                pass

    def get_model_from_cached_json_db(self, model):
        data = self.local_model_metadata.get(model)
        if data:
            return data

        # Ensure cache is loaded before checking content
        self._load_cache()

        if not self.content:
            self._update_cache()

        if not self.content:
            return dict()

        info = self.content.get(model, dict())
        if info:
            return info

        pieces = model.split("/")
        if len(pieces) == 2:
            info = self.content.get(pieces[1])
            if info and info.get("litellm_provider") == pieces[0]:
                return info

        return dict()

    def get_model_info(self, model):
        cached_info = self.get_model_from_cached_json_db(model)

        litellm_info = None
        if litellm._lazy_module or not cached_info:
            try:
                litellm_info = litellm.get_model_info(model)
            except Exception as ex:
                if "model_prices_and_context_window.json" not in str(ex):
                    print(str(ex))

        if litellm_info:
            return litellm_info

        if not cached_info and model.startswith("openrouter/"):
            # First try using the locally cached OpenRouter model database
            openrouter_info = self.openrouter_manager.get_model_info(model)
            if openrouter_info:
                return openrouter_info

            # Fallback to legacy web-scraping if the API cache does not contain the model
            openrouter_info = self.fetch_openrouter_model_info(model)
            if openrouter_info:
                return openrouter_info

        return cached_info

    def fetch_openrouter_model_info(self, model):
        """
        Fetch model info by scraping the openrouter model page.
        Expected URL: https://openrouter.ai/<model_route>
        Example: openrouter/qwen/qwen-2.5-72b-instruct:free
        Returns a dict with keys: max_tokens, max_input_tokens, max_output_tokens,
        input_cost_per_token, output_cost_per_token.
        """
        url_part = model[len("openrouter/") :]
        url = "https://openrouter.ai/" + url_part
        try:
            import requests

            response = requests.get(url, timeout=5, verify=self.verify_ssl)
            if response.status_code != 200:
                return {}
            html = response.text
            import re

            if re.search(
                rf"The model\s*.*{re.escape(url_part)}.* is not available", html, re.IGNORECASE
            ):
                print(f"\033[91mError: Model '{url_part}' is not available\033[0m")
                return {}
            text = re.sub(r"<[^>]+>", " ", html)
            context_match = re.search(r"([\d,]+)\s*context", text)
            if context_match:
                context_str = context_match.group(1).replace(",", "")
                context_size = int(context_str)
            else:
                context_size = None
            input_cost_match = re.search(r"\$\s*([\d.]+)\s*/M input tokens", text, re.IGNORECASE)
            output_cost_match = re.search(r"\$\s*([\d.]+)\s*/M output tokens", text, re.IGNORECASE)
            input_cost = float(input_cost_match.group(1)) / 1000000 if input_cost_match else None
            output_cost = float(output_cost_match.group(1)) / 1000000 if output_cost_match else None
            if context_size is None or input_cost is None or output_cost is None:
                return {}
            params = {
                "max_input_tokens": context_size,
                "max_tokens": context_size,
                "max_output_tokens": context_size,
                "input_cost_per_token": input_cost,
                "output_cost_per_token": output_cost,
            }
            return params
        except Exception as e:
            print("Error fetching openrouter info:", str(e))
            return {}
        

model_info_manager = ModelInfoManager()
