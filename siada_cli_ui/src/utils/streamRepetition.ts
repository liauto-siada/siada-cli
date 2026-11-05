/**
 * Stream repetition guard for repetition-prone models
 * (deepseek-v4-flash family and lpai-glm-5.3).
 *
 * Mirrors siada/entrypoint/interaction/turn/stream_repetition.py — keep the
 * constants in sync. The UI side uses this to HOLD rendering of a suspicious
 * stream (stop flushing deltas) until the backend confirms the abort via a
 * `stream_aborted` lifecycle event (backend detected the same repetition and
 * is retrying the request). If the stream ends normally instead, the hold was
 * a false positive and the accumulated content is flushed as usual.
 */

/** Substring match so "kivy-deepseek-v4-flash" and dated variants
 *  ("kivy-deepseek-v4-flash-0731") are all covered. */
export const REPETITION_GUARD_MODEL_MARKERS = ['deepseek-v4-flash'];

export function isRepetitionGuardModel(model: string | undefined | null): boolean {
  if (!model) return false;
  const lowered = model.toLowerCase();
  return REPETITION_GUARD_MODEL_MARKERS.some((marker) => lowered.includes(marker));
}

export interface RepetitionHit {
  unit: string;
  repeats: number;
}

export class StreamRepetitionDetector {
  // Tail window kept for analysis (chars).
  static readonly WINDOW = 4096;
  // Run the check every N newly fed chars.
  static readonly CHECK_EVERY = 64;
  // Unit length bounds. MIN_UNIT=8 filters out benign short repeats
  // (list markers, whitespace runs) while still catching dense CJK loops
  // (a 14-char Chinese sentence is a plausible repetition unit).
  static readonly MIN_UNIT = 8;
  static readonly MAX_UNIT = 600;
  // Tail must end with at least this many consecutive copies of the unit.
  static readonly MIN_REPEATS = 3;
  // The repeating unit must contain at least this many distinct
  // non-whitespace characters -- otherwise long divider runs ("=" x 80,
  // markdown rules) would false-positive.
  static readonly MIN_DISTINCT_CHARS = 3;

  // Sentence-frequency check: catches "fuzzy" loops where the model cycles
  // through near-identical deliberation sentences (with small variations)
  // that the exact-unit check above can only catch once the loop degenerates
  // into verbatim repeats. If any sentence of >= SENT_MIN_LEN chars appears
  // >= SENT_MAX_COUNT times inside the tail window, the stream is looping.
  static readonly SENT_SPLIT_RE = /(?<=[.!?。！？\n])\s+/;
  static readonly SENT_MIN_LEN = 10;
  static readonly SENT_MAX_COUNT = 3;

  private tail = '';
  private sinceCheck = 0;
  fired = false;
  hit: RepetitionHit | null = null;
  kind: 'exact' | 'sentence' | null = null;

  /** Feed a streamed delta; returns the hit on first detection, else null. */
  feed(delta: string): RepetitionHit | null {
    if (this.fired || !delta) return this.hit;
    this.tail = (this.tail + delta).slice(-StreamRepetitionDetector.WINDOW);
    this.sinceCheck += delta.length;
    if (this.sinceCheck < StreamRepetitionDetector.CHECK_EVERY) return null;
    this.sinceCheck = 0;
    return this.check();
  }

  private check(): RepetitionHit | null {
    const tail = this.tail;
    const n = tail.length;
    const maxUnit = Math.min(
      StreamRepetitionDetector.MAX_UNIT,
      Math.floor(n / StreamRepetitionDetector.MIN_REPEATS),
    );
    for (let unitLen = StreamRepetitionDetector.MIN_UNIT; unitLen <= maxUnit; unitLen++) {
      const unit = tail.slice(n - unitLen);
      if (new Set(unit.replace(/\s/g, '')).size < StreamRepetitionDetector.MIN_DISTINCT_CHARS) {
        continue;
      }
      let repeats = 1;
      let pos = n - unitLen;
      while (pos - unitLen >= 0 && tail.slice(pos - unitLen, pos) === unit) {
        repeats++;
        pos -= unitLen;
      }
      if (repeats >= StreamRepetitionDetector.MIN_REPEATS) {
        this.fired = true;
        this.kind = 'exact';
        this.hit = { unit, repeats };
        return this.hit;
      }
    }
    return this.checkSentenceFrequency();
  }

  /**
   * Fuzzy-loop check: any single sentence recurring too often in the tail
   * window means the model is cycling through near-identical text.
   */
  private checkSentenceFrequency(): RepetitionHit | null {
    const D = StreamRepetitionDetector;
    const counts = new Map<string, number>();
    for (const raw of this.tail.split(D.SENT_SPLIT_RE)) {
      const s = raw.trim();
      if (s.length < D.SENT_MIN_LEN) continue;
      counts.set(s, (counts.get(s) ?? 0) + 1);
    }
    let best: string | null = null;
    let bestCount = 0;
    for (const [s, n] of counts) {
      if (n > bestCount) {
        best = s;
        bestCount = n;
      }
    }
    if (best !== null && bestCount >= D.SENT_MAX_COUNT) {
      this.fired = true;
      this.kind = 'sentence';
      this.hit = { unit: best, repeats: bestCount };
      return this.hit;
    }
    return null;
  }
}
