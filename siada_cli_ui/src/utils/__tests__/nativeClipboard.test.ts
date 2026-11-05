import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NativeClipboardClient } from '../nativeClipboard.js';
import { PNG } from 'pngjs';

const fixture = fileURLToPath(new URL('./fixtures/native-clipboard.cjs', import.meta.url));
const clients: NativeClipboardClient[] = [];
function client(timeout = 1000): NativeClipboardClient {
  const value = new NativeClipboardClient(fixture, timeout);
  clients.push(value);
  return value;
}
afterEach(() => {
  clients.splice(0).forEach(value => value.dispose());
  vi.unstubAllEnvs();
});

describe('native clipboard subprocess boundary', () => {
  it('returns non-square PNG dimensions and unchanged RGBA pixels', async () => {
    const image = await client().readImage();
    expect(image).toMatchObject({ width: 2, height: 3 });
    const decoded = PNG.sync.read(image!.data);
    expect(decoded.width).toBe(2);
    expect(decoded.height).toBe(3);
    expect([...decoded.data]).toEqual([
      255, 0, 0, 255, 0, 255, 0, 128,
      0, 0, 255, 255, 255, 255, 0, 64,
      255, 0, 255, 255, 0, 255, 255, 255,
    ]);
  });

  it('reports an absent image without inventing an attachment', async () => {
    const clipboard = client();
    await clipboard.writeText('no-image');
    expect(await clipboard.readImage()).toBeNull();
  });

  it.each(['invalid-image', 'wrong-image-size'])('rejects %s and permits a later valid image', async failure => {
    const clipboard = client();
    await clipboard.writeText(failure);
    await expect(clipboard.readImage()).rejects.toThrow();
    expect(await clipboard.readImage()).toMatchObject({ width: 2, height: 3 });
  });

  it('preserves the text owner when the image backend is unavailable', async () => {
    const clipboard = client();
    await clipboard.writeText('image-unavailable');
    await expect(clipboard.readImage()).rejects.toThrow();
    expect(await clipboard.readText()).toBe('image-unavailable');
  });
  it('passes desktop configuration without forwarding credentials or a native-library override', async () => {
    vi.stubEnv('DISPLAY', ':99');
    vi.stubEnv('SIADA_CLIPBOARD_TEST_SECRET', 'synthetic-secret');
    vi.stubEnv('NAPI_RS_NATIVE_LIBRARY_PATH', '/synthetic/override.node');
    const clipboard = client();
    await clipboard.writeText('inspect-env');
    expect(JSON.parse(await clipboard.readText())).toEqual({ display: ':99' });
  });
  it('retains ownership between writes and reads and preserves Unicode and whitespace', async () => {
    const clipboard = client();
    const text = '  中文👩‍💻\r\nsecond line\n"\\\x1b[2J  ';
    await clipboard.writeText(text);
    expect(await clipboard.readText()).toBe(text);
    expect(await clipboard.readText()).toBe(text);
  });

  it('serializes concurrent operations without cross-request contamination', async () => {
    const clipboard = client();
    const results = await Promise.all([
      clipboard.writeText('first'), clipboard.readText(),
      clipboard.writeText('second'), clipboard.readText(),
    ]);
    expect(results).toEqual([undefined, 'first', undefined, 'second']);
  });

  it.each(['crash', 'invalid', 'wrong-id', 'failed'])('recovers after %s', async failure => {
    const clipboard = client();
    await expect(clipboard.writeText(failure)).rejects.toThrow('Native clipboard unavailable');
    await clipboard.writeText('recovered');
    expect(await clipboard.readText()).toBe('recovered');
  });

  it('kills a hung native operation after the deadline and permits retry', async () => {
    const clipboard = client(150);
    await expect(clipboard.writeText('hang')).rejects.toThrow();
    await clipboard.writeText('retry');
    expect(await clipboard.readText()).toBe('retry');
  });

  it('cancels an active write and starts a clean helper for the next request', async () => {
    const clipboard = client();
    const abort = new AbortController();
    const pending = clipboard.writeText('hang', abort.signal);
    setTimeout(() => abort.abort(), 50);
    await expect(pending).rejects.toThrow();
    await clipboard.writeText('after cancellation');
    expect(await clipboard.readText()).toBe('after cancellation');
  });

  it('rejects a cancelled queued write without changing the clipboard', async () => {
    const clipboard = client();
    const abort = new AbortController();
    const first = clipboard.writeText('kept');
    const second = clipboard.writeText('cancelled', abort.signal);
    abort.abort();
    await first;
    await expect(second).rejects.toThrow();
    expect(await clipboard.readText()).toBe('kept');
  });

  it('rejects an oversized write before starting the helper', async () => {
    const clipboard = client();
    await expect(clipboard.writeText('中'.repeat(33334))).rejects.toThrow();
    expect(await clipboard.readText()).toBe('');
  });
});