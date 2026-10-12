"""Bounded matching tolerance without semantic or whole-file normalization."""

import importlib

import pytest

from siada.tools.coder.native_patch_diff import PatchContextError, apply_native_diff


@pytest.mark.parametrize(
    "source, old_line",
    [
        ('title: “Q4—report”', 'title: "Q4-report"'),
        ('"id":\u00a0"summary",', '"id": "summary",'),
        ("value: ‘can’t’", "value: 'can't'"),
        ("label: a\u3000b", "label: a b"),
        ("\told   ", "old"),
    ],
)
def test_matching_tolerates_only_bounded_punctuation_and_whitespace(source, old_line):
    diff = f"@@\n-{old_line}\n+changed\n"
    assert apply_native_diff(source + "\n", diff, mode="default") == "changed\n"


def test_exact_match_precedes_unicode_fallback():
    source = 'title: “Q4—report”\ntitle: "Q4-report"\n'
    diff = '@@\n-title: "Q4-report"\n+changed\n'
    assert apply_native_diff(source, diff, mode="default") == 'title: “Q4—report”\nchanged\n'


def test_untouched_unicode_indent_and_mixed_line_endings_are_preserved():
    source = "  title: “Q4—report”  \r\nold\nlast\r"
    diff = '@@\n title: "Q4-report"\n-old\n+new “value”\n last\n'
    assert apply_native_diff(source, diff, mode="default") == (
        "  title: “Q4—report”  \r\nnew “value”\r\nlast\r"
    )


@pytest.mark.parametrize(
    "source, old_line",
    [
        ('"id": "summary",\n"dissolve": true,\n', '"id": "summary", "dissolve": true,'),
        ('"dissolve": false,\n', '"dissolve": true,'),
        ('"id":  "summary",\n', '"id": "summary",'),
        ('"id": "summary", "dissolve": true,\n', '"dissolve": true,'),
        ('"id": "summary"\n', '"id": "summary",'),
        ("old\n", "    12\told"),
    ],
)
def test_changed_values_reflow_substrings_and_reader_numbers_are_rejected(source, old_line):
    with pytest.raises(PatchContextError, match="Invalid Context"):
        apply_native_diff(source, f"@@\n-{old_line}\n+changed\n", mode="default")


@pytest.mark.parametrize("suffix", ["", "\n", "\r\n"])
@pytest.mark.parametrize("eof_marker", ["", "*** End of File\n"])
def test_trailing_empty_context_is_tolerated_only_at_file_end(suffix, eof_marker):
    diff = "@@\n-target\n+changed\n \n" + eof_marker
    expected = "changed" + suffix
    assert apply_native_diff("target" + suffix, diff, mode="default") == expected


def test_missing_blank_context_in_middle_of_file_is_not_ignored():
    with pytest.raises(PatchContextError):
        apply_native_diff("target\nother\n", "@@\n-target\n+changed\n \n", mode="default")


def test_trailing_context_sentinel_does_not_displace_insertions():
    diff = "@@\n target\n \n+new\n*** End of File\n"
    assert apply_native_diff("target", diff, mode="default") == "target\nnew"


def test_unicode_anchors_locate_the_target_without_normalizing_source():
    source = "heading: Q4—report\nold\nother\n"
    diff = "@@ heading: Q4-report\n-old\n+new\n"
    assert apply_native_diff(source, diff, mode="default") == "heading: Q4—report\nnew\nother\n"


def test_stacked_anchors_preserve_sdk_contract():
    source = "class First\n method\n old\nclass Second\n method\n old\n"
    diff = "@@ class Second\n@@ method\n-old\n+new\n"
    assert apply_native_diff(source, diff, mode="default").endswith("class Second\n method\nnew\n")
    with pytest.raises(PatchContextError, match="Invalid Anchor"):
        apply_native_diff(source, "@@ missing\n@@ method\n-old\n+new\n", mode="default")


@pytest.mark.parametrize(
    "source, diff",
    [
        ("one\ntwo\n", "@@\n one\n-two\n+three\n"),
        ("one\r\ntwo\r\n", "@@\n one\n-two\n+three\n"),
        ("one\ntwo", "@@\n-two\n+three\n"),
        ("one\n", "@@\n one\n+two\n*** End of File\n"),
        ("one\ntwo\n", "@@\n-one\n+first\n@@\n-two\n+second\n"),
        ("one\ntwo\n", "@@\n+first\n"),
    ],
)
def test_successful_ordinary_diffs_keep_sdk_output(source, diff):
    sdk_diff = importlib.import_module("agents.apply_diff")
    assert apply_native_diff(source, diff, mode="default") == sdk_diff.apply_diff(source, diff)


def test_overlapping_hunks_are_rejected():
    diff = "@@\n-one\n+first\n*** End of File\n@@\n-one\n+second\n*** End of File\n"
    with pytest.raises(ValueError):
        apply_native_diff("one\n", diff, mode="default")
