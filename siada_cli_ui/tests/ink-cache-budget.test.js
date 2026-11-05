import { describe, expect, it } from 'vitest';
import { DataLimitedLruMap } from '../node_modules/@jrichman/ink/build/data-limited-lru-map.js';

describe('Ink cache data budget', () => {
  it('rejects oversized output and preserves replacement accounting', () => {
    const cache = new DataLimitedLruMap(5, 20);
    cache.set('small', 1);
    cache.set('small', 2);
    cache.set('x'.repeat(21), 3);
    expect(cache.get('small')).toBe(2);
    expect(cache.get('x'.repeat(21))).toBeUndefined();
    expect(cache.currentDataSizeValue).toBe(5);
  });
  it('releases the backing-array references when the data budget evicts a value', () => {
    const cache = new DataLimitedLruMap(100, 10);
    const first = { retained: true };
    cache.set('aaaaaa', first);
    cache.set('bbbbbb', {});
    expect(cache.get('aaaaaa')).toBeUndefined();
    expect(cache.map.K).not.toContain('aaaaaa');
    expect(cache.map.V).not.toContain(first);
  });
  it('stays within both budgets through repeated eviction and replacement', () => {
    const cache = new DataLimitedLruMap(5, 20);
    for (let i = 0; i < 1000; i++) {
      const key = String(i).padStart(4, '0');
      cache.set(key, i); cache.set(key, i + 1);
      expect(cache.get(key)).toBe(i + 1);
      expect(cache.currentDataSizeValue).toBe(cache.size * 4);
      expect(cache.currentDataSizeValue).toBeLessThanOrEqual(20);
      expect(cache.size).toBeLessThanOrEqual(5);
    }
  });
});