from dataclasses import dataclass, fields
from typing import Optional

from siada.models.model_base_config import DEFAULT_MODEL_NAME, ModelBaseConfig, get_model_config, get_model_settings


import os
from pathlib import Path

import logging
import yaml
@dataclass()
class ModelRunConfig(ModelBaseConfig):
    
    reasoning_effort : Optional[str] = None
    # The user's effort intent BEFORE cross-model mapping (e.g. "xhigh" set
    # on Claude, carried to GLM-5.3 as "max"). Kept across model switches so
    # the original level survives chained switches without mapping drift.
    user_reasoning_effort : Optional[str] = None
    thinking_tokens : Optional[int] = None
    enable_thinking : Optional[bool] = None  # Explicit enable/disable thinking (None = not configured)
    temperature : Optional[float] = None
    extra_params : Optional[dict] = None
    provider: Optional[str] = None


    def __init__(self, model): 
        self.configure_model_settings(model)


    def _copy_fields(self, source):
        """Helper to copy fields from a ModelSettings instance to self"""
        for field in fields(ModelBaseConfig):
            val = getattr(source, field.name)
            setattr(self, field.name, val)


    def configure_model_settings(self, model):
        # Look for exact model match
        model_config = get_model_config(model)
        if not model_config:
            logger = logging.getLogger(__name__)
            logger.warning(f"Model {model} not found in model settings, falling back to {DEFAULT_MODEL_NAME}")
            model_config = get_model_config(DEFAULT_MODEL_NAME)

        if model_config:
            self._copy_fields(model_config)
            # Reset thinking_tokens and reasoning_effort to avoid stale values
            self.thinking_tokens = None
            self.reasoning_effort = None
            self.temperature = None
            # Apply default thinking tokens if the new model has them configured
            if model_config.default_thinking_tokens:
                self.thinking_tokens = model_config.default_thinking_tokens
                self.temperature = None  # thinking mode requires temperature=None
            # Apply default reasoning effort if the new model has it configured
            if model_config.default_reasoning_effort:
                self.reasoning_effort = model_config.default_reasoning_effort
        else:
            raise ValueError(f"Model {model} not found in model settings")
        

    def set_reasoning_effort(self, reasoning_effort):
        # Explicitly setting an effort also records the user intent, so it can
        # be re-mapped (not lost) when switching models in-session.
        self.reasoning_effort = reasoning_effort
        self.user_reasoning_effort = reasoning_effort

    def carry_over_reasoning_settings(self, old_config) -> Optional[tuple]:
        """Carry the user's /thinking and /effort settings from the previous
        model's config onto this one (the new model), mapping the effort onto
        a level the new model accepts.

        Called by /model so session-level reasoning settings survive model
        switches. Only USER-set values are carried — model defaults are not
        (every model keeps its own).

        Returns ``(original_effort, mapped_effort)`` when a user-set effort
        was carried over, otherwise ``None``.
        """
        if old_config is None:
            return None

        # /thinking: a boolean on/off switch, meaningful for every model.
        old_thinking = getattr(old_config, "enable_thinking", None)
        if old_thinking is not None:
            self.enable_thinking = old_thinking
            if old_thinking is False:
                # Mirror the startup behaviour: disabling clears any token budget.
                self.thinking_tokens = None

        # /effort: only the user's explicit intent is carried. When the
        # user_reasoning_effort marker is missing (config built without it),
        # fall back to "differs from the previous model's default" as the
        # signal that the user set it manually.
        user_effort = getattr(old_config, "user_reasoning_effort", None)
        if user_effort is None:
            old_effort = getattr(old_config, "reasoning_effort", None)
            old_default = getattr(old_config, "default_reasoning_effort", None)
            if old_effort is not None and old_effort != old_default:
                user_effort = old_effort
        if user_effort is None:
            return None

        # Keep the original intent even when the new model cannot express it
        # (e.g. GLM-5.2 takes no reasoning_effort param at all), so a later
        # switch to a supporting model restores it.
        self.user_reasoning_effort = user_effort
        supports = self.supports_extra_params or []
        if "reasoning_effort" not in supports:
            return None

        from siada.models.model_base_config import coerce_reasoning_effort
        mapped = coerce_reasoning_effort(
            self.model_name, user_effort, self.default_reasoning_effort
        )
        self.reasoning_effort = mapped
        return (user_effort, mapped)


    def get_raw_thinking_tokens(self):
        """Get formatted thinking token budget if available"""
        return self.thinking_tokens

    def get_thinking_tokens(self):
        budget = self.get_raw_thinking_tokens()

        # For models that only support adaptive thinking, always show "adaptive"
        if budget is not None and self.default_thinking_tokens == -1:
            return "adaptive"
        if budget == -1:
            return "adaptive"
        if budget is not None:
            # Format as xx.yK for thousands, xx.yM for millions
            if budget >= 1024 * 1024:
                value = budget / (1024 * 1024)
                if value == int(value):
                    return f"{int(value)}M"
                else:
                    return f"{value:.1f}M"
            else:
                value = budget / 1024
                if value == int(value):
                    return f"{int(value)}k"
                else:
                    return f"{value:.1f}k"
        return None
    
    def get_reasoning_effort(self):
        """Get reasoning effort value if available"""
        return self.reasoning_effort
    
    

    def set_thinking_tokens(self, value):
        """
        Set the thinking token budget for models that support it.
        Accepts formats: 8096, "8k", "10.5k", "0.5M", "10K", etc.
        Pass "0" to disable thinking tokens.
        """
        if value is not None:
            num_tokens = self.parse_token_value(value)
            self.temperature = None
            if num_tokens > 0:
                self.thinking_tokens = num_tokens
            else:
                self.thinking_tokens = None


    def parse_token_value(self, value):
        """
        Parse a token value string into an integer.
        Accepts formats: 8096, "8k", "10.5k", "0.5M", "10K", etc.

        Args:
            value: String or int token value

        Returns:
            Integer token value
        """
        if isinstance(value, int):
            return value

        if not isinstance(value, str):
            return int(value)  # Try to convert to int

        value = value.strip().upper()

        if value.endswith("K"):
            multiplier = 1024
            value = value[:-1]
        elif value.endswith("M"):
            multiplier = 1024 * 1024
            value = value[:-1]
        else:
            multiplier = 1

        # Convert to float first to handle decimal values like "10.5k"
        return int(float(value) * multiplier)
    

    @staticmethod
    def get_default_config():
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "agent_config.yaml"
        llm_config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    llm_config = config.get('llm_config', {})
            except Exception as e:
                    logging.warning(f"Failed to read agent config file for repo map instance: {str(e)}")
        model_name = llm_config.get('model_name')
        provider = llm_config.get('provider')

        try:
            model_config = ModelRunConfig(model_name)
        except ValueError:
            # agent_config.yaml holds a framework default model (e.g.
            # kivy-kimi-k3) that may not exist in the currently active model
            # settings — this happens when a 'default' provider's model list has
            # replaced the built-in MODEL_SETTING (e.g. on the feishu daemon's
            # 2nd+ message). This baseline is only a seed: callers either override
            # the model immediately (get_config) or only read `.provider`. Build a
            # valid baseline from any available model so we don't crash, while
            # keeping the configured model_name/provider.
            settings = get_model_settings()
            if settings:
                model_config = ModelRunConfig(settings[0].model_name)
                model_config.model_name = model_name
            else:
                raise

        model_config.provider = provider
        return model_config








