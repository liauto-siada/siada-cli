"""Unit tests for ``prompt_builder`` memory-section framing.

The contract verified here:

1. ``wrap_user_memory`` wraps the combined-memory snapshot in a titled
   ``====`` section so the model can tell where the snapshot begins and
   ends.
2. ``build_system_prompt`` ships that framed section at the tail of the
   system prompt (instead of concatenating the raw memory bare), and
   skips the section entirely when no memory is available.
3. Whitespace-only memory is treated as absent, mirroring the historical
   guard behaviour.
"""

from siada.agent_hub.coder.prompt.base.prompt_builder import (
    MEMORY_SECTION_TITLE,
    build_system_prompt,
    wrap_user_memory,
)


def test_wrap_user_memory_produces_titled_section():
    wrapped = wrap_user_memory("some memory body")
    assert wrapped == f"====\n{MEMORY_SECTION_TITLE}\n\nsome memory body\n===="


def test_wrap_user_memory_strips_surrounding_whitespace():
    wrapped = wrap_user_memory("\n  some memory body  \n")
    assert wrapped == f"====\n{MEMORY_SECTION_TITLE}\n\nsome memory body\n===="


def test_build_system_prompt_frames_memory_with_outer_title():
    prompt = build_system_prompt(
        intro="intro",
        capabilities="capabilities",
        rules="rules",
        objective="objective",
        user_memory="====\nInline Memory\n\nbody\n====",
    )
    # The combined-memory snapshot must ship inside the outer titled
    # section at the tail of the prompt.
    assert f"====\n{MEMORY_SECTION_TITLE}\n" in prompt
    assert prompt.rstrip().endswith("====")
    pos_title = prompt.find(MEMORY_SECTION_TITLE)
    pos_inner = prompt.find("Inline Memory")
    assert -1 < pos_title < pos_inner


def test_build_system_prompt_skips_memory_section_when_absent():
    prompt = build_system_prompt(
        intro="intro",
        capabilities="capabilities",
        rules="rules",
        objective="objective",
        user_memory=None,
    )
    assert MEMORY_SECTION_TITLE not in prompt


def test_build_system_prompt_skips_memory_section_when_blank():
    prompt = build_system_prompt(
        intro="intro",
        capabilities="capabilities",
        rules="rules",
        objective="objective",
        user_memory="   \n  ",
    )
    assert MEMORY_SECTION_TITLE not in prompt
