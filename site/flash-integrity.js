// Fail closed before exposing the USB installation control.
export async function verifyFirmware(buffer, expected) {
  const bytes = new Uint8Array(buffer);
  if (bytes.length !== expected.bytes || bytes.length < 24) throw new Error('Firmware size mismatch');
  if (bytes[0] !== 0xe9 || new DataView(buffer).getUint16(12, true) !== 9) throw new Error('Not an ESP32-S3 firmware image');
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  const hex = [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, '0')).join('');
  if (hex !== expected.sha256) throw new Error('Firmware checksum mismatch');
  return hex;
}
