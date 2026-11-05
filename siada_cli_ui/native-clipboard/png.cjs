const SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const MAX_PNG_BYTES = 20 * 1024 * 1024;
const MAX_PIXELS = 40_000_000;

/** Read dimensions from the encoded PNG, never infer them from RGBA length. */
function decodePng(base64) {
  if (typeof base64 !== 'string' || base64.length > Math.ceil(MAX_PNG_BYTES * 4 / 3) + 4) {
    throw new Error('Invalid native clipboard image');
  }
  const data = Buffer.from(base64, 'base64');
  if (data.toString('base64').replace(/=+$/, '') !== base64.replace(/=+$/, '') ||
      data.length < 45 || data.length > MAX_PNG_BYTES ||
      !data.subarray(0, 8).equals(SIGNATURE) ||
      data.readUInt32BE(8) !== 13 || data.toString('ascii', 12, 16) !== 'IHDR' ||
      data.readUInt32BE(data.length - 12) !== 0 ||
      data.toString('ascii', data.length - 8, data.length - 4) !== 'IEND') {
    throw new Error('Invalid native clipboard image');
  }
  const width = data.readUInt32BE(16);
  const height = data.readUInt32BE(20);
  if (!width || !height || width > 32768 || height > 32768 || width * height > MAX_PIXELS) {
    throw new Error('Invalid native clipboard image dimensions');
  }
  return { data, width, height };
}

module.exports = { decodePng };