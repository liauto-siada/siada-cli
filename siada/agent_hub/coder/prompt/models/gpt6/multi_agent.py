"""Codex V2 explicit-request delegation rule adapted to Siada.

Source: openai/codex commit 83086188ae0614bd882818ff1aa23f3194962012,
codex-rs/prompts/src/model_messages/multi_agent.rs. OpenAI Codex, Copyright 2025 OpenAI.
Apache-2.0; the license and attribution are reproduced in docs/CREDITS.md.
"""


EXPLICIT_REQUEST_ONLY = (
    "Any earlier instruction enabling proactive multi-agent delegation no longer applies. "
    "Do not spawn sub-agents unless the user or applicable SIADA.md/AGENTS.md/skill "
    "instructions explicitly ask for sub-agents, delegation, or parallel agent work."
)