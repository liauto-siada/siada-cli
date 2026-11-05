// Native calls run outside the TUI. Keep the instance alive to retain Linux
// selection ownership; closing stdin releases it when the TUI exits.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const readline = require('node:readline');
const { decodePng } = require('./png.cjs');

let clipboard;
let imageClipboard;
const MAX_BYTES = 30 * 1024 * 1024;
const remote = process.env.SSH_TTY || process.env.SSH_CONNECTION || process.env.SSH_CLIENT;
const wsl = process.platform === 'linux' && (
  process.env.WSL_DISTRO_NAME || process.env.WSL_INTEROP || /microsoft/i.test(os.release())
);
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on('close', () => process.exit(0));
input.on('line', async line => {
  let request;
  try {
    if (Buffer.byteLength(line) > MAX_BYTES) throw new Error('too large');
    request = JSON.parse(line);
    if (!Number.isSafeInteger(request.id) || !['read', 'write', 'image'].includes(request.operation)) {
      throw new Error('invalid request');
    }
    if (remote || wsl) throw new Error('host clipboard unavailable');
    if (request.operation === 'image') {
      if (!imageClipboard) {
        const runtime = path.join(__dirname, 'image-runtime', 'index.js');
        imageClipboard = fs.existsSync(runtime)
          ? require(runtime) : require('@mariozechner/clipboard');
      }
      let image = null;
      if (imageClipboard.hasImage()) {
        // The native binding reads dimensions and pixels, then encodes PNG in
        // Rust. Its getImageBase64 result is PNG, not an unlabelled RGBA buffer.
        const png = await imageClipboard.getImageBase64();
        const { width, height } = decodePng(png);
        image = { png, width, height };
      }
      process.stdout.write(JSON.stringify({ id: request.id, ok: true, image }) + '\n');
      return;
    }
    if (!clipboard) {
      const runtime = path.join(__dirname, 'runtime', 'index.js');
      const { Clipboard } = fs.existsSync(runtime)
        ? require(runtime) : require('@napi-rs/clipboard');
      clipboard = new Clipboard();
    }
    let text;
    if (request.operation === 'read') {
      try {
        text = clipboard.getText();
      } catch (error) {
        // An empty clipboard or a clipboard containing only an image is a
        // successful text read with no text, not a missing native backend.
        if (/not available in the requested format/i.test(String(error))) text = '';
        else throw error;
      }
      if (typeof text !== 'string' || Buffer.byteLength(text) > MAX_BYTES - 1024) {
        throw new Error('invalid response');
      }
    } else {
      if (typeof request.text !== 'string' || Buffer.byteLength(request.text) > 100000) {
        throw new Error('invalid text');
      }
      clipboard.setText(request.text);
    }
    process.stdout.write(JSON.stringify({ id: request.id, ok: true, text }) + '\n');
  } catch {
    // Never expose clipboard content, native diagnostics or escape sequences
    // through this transport or application logs.
    process.stdout.write(JSON.stringify({ id: request?.id, ok: false }) + '\n');
  }
});