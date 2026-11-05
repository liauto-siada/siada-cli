// Run against the packaged client/helper under an isolated Xvfb display.
// This exercises real arboard ownership without accessing a user's clipboard.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { setTimeout as pause } from 'node:timers/promises';

const { NativeClipboardClient } = await import(pathToFileURL(process.argv[2]).href);
for (const command of ['wl-paste', 'xclip', 'wl-copy']) {
  assert.throws(() => execFileSync(command, ['--version'], { stdio: 'ignore' }));
}
const owner = new NativeClipboardClient(process.argv[3]);
const reader = new NativeClipboardClient(process.argv[3]);
try {
  const text = '  中文 native 👩‍💻\nsecond line\n  ';
  await owner.writeText(text);
  await pause(200);
  assert.equal(await reader.readText(), text);
  await reader.writeText('replaced externally');
  assert.equal(await owner.readText(), 'replaced externally');
  await owner.writeText(text);
  assert.equal(await reader.readText(), text);
  console.log('PASS: native X11 Unicode, multiline, ownership and repeated copying without clipboard commands');
} finally {
  owner.dispose();
  reader.dispose();
}