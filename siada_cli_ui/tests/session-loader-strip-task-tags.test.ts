import { describe, it, expect } from 'vitest';
import { stripTaskTags } from '../src/services/sessionLoader.js';

// Mirrors the Python-side wrap_user_input / strip_user_input tests
// (tests/services/memory/holographic/test_marker.py) — the backend wraps
// every raw user input in a <user_input>...</user_input> tag (see
// siada/services/memory/holographic/marker.py), and this helper is the
// frontend-side counterpart that recovers the human's literal text for
// display in the session list / history.
describe('stripTaskTags', () => {
  it('strips the legacy <task>...</task> wrapper and discards the tail', () => {
    expect(stripTaskTags('<task>Do the thing</task>\nSome trailing context')).toBe(
      'Do the thing'
    );
  });

  it('strips the <user_input> wrapper and discards the tail', () => {
    expect(stripTaskTags('<user_input>Hello there</user_input>\nSome trailing context')).toBe(
      'Hello there'
    );
  });

  it('uses the same start/end boundaries as <task>', () => {
    expect(
      stripTaskTags('prefix\n<user_input>Hello</user_input>\n<!--IM_CONTEXT_INJECTION:BEGIN-->meta<!--IM_CONTEXT_INJECTION:END-->')
    ).toBe('prefix\n<user_input>Hello');
  });

  it('stops at the first closing <user_input> tag', () => {
    expect(stripTaskTags('<user_input>a</user_input> and <user_input>b</user_input>')).toBe(
      'a'
    );
  });

  it('is a no-op when no tags are present', () => {
    expect(stripTaskTags('plain text, no tags')).toBe('plain text, no tags');
  });

  it('trims surrounding whitespace', () => {
    expect(stripTaskTags('  <user_input>padded</user_input>  ')).toBe('padded');
  });
});
