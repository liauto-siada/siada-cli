const readline = require('node:readline');
const { PNG } = require('pngjs');
let text = '';
const input = readline.createInterface({ input: process.stdin });
input.on('close', () => process.exit(0));
input.on('line', line => {
  const request = JSON.parse(line);
  if (request.operation === 'image') {
    if (text === 'image-unavailable') {
      return process.stdout.write(JSON.stringify({ id: request.id, ok: false }) + '\n');
    }
    const png = PNG.sync.write({
      width: 2, height: 3,
      data: Buffer.from([
        255, 0, 0, 255, 0, 255, 0, 128,
        0, 0, 255, 255, 255, 255, 0, 64,
        255, 0, 255, 255, 0, 255, 255, 255,
      ]),
    });
    const image = text === 'no-image' ? null : {
      png: text === 'invalid-image' ? Buffer.from('RGBA is not PNG').toString('base64') : png.toString('base64'),
      width: text === 'wrong-image-size' ? 3 : 2, height: 3,
    };
    return process.stdout.write(JSON.stringify({ id: request.id, ok: true, image }) + '\n');
  }
  if (request.text === 'hang') return;
  if (request.text === 'crash') return process.exit(2);
  if (request.text === 'invalid') return process.stdout.write('not JSON\n');
  if (request.text === 'wrong-id') {
    return process.stdout.write(JSON.stringify({ id: -1, ok: true }) + '\n');
  }
  if (request.text === 'failed') {
    return process.stdout.write(JSON.stringify({ id: request.id, ok: false }) + '\n');
  }
  if (request.operation === 'write') text = request.text;
  if (text === 'inspect-env') text = JSON.stringify({
    display: process.env.DISPLAY,
    secret: process.env.SIADA_CLIPBOARD_TEST_SECRET,
    override: process.env.NAPI_RS_NATIVE_LIBRARY_PATH,
  });
  process.stdout.write(JSON.stringify({
    id: request.id, ok: true, text: request.operation === 'read' ? text : undefined,
  }) + '\n');
});