// Replace null with the real public apps.apple.com listing when Apple publishes it.
// Do not use an App Store search URL or an unsigned IPA as a store destination.
export const appStoreUrl = null;
export function publicAppStoreUrl(value = appStoreUrl) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'apps.apple.com' && /\/id\d+$/.test(url.pathname) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
export const firmware = Object.freeze({
  path: './firmware/Wappai-1.75C-factory.bin',
  version: '1.0.0-dev.1',
  bytes: 3455040,
  sha256: 'ed8f6600a79160ba2b54b7beb6c3b4c7e0c775e1bcf8e124feb6c63a532508b9',
});

export const boardNames = Object.freeze({
  'ws-s3-175c':'Waveshare 1.75C', 'ws-s3-175':'Waveshare 1.75',
  'ws-s3-18':'Waveshare 1.8', 'ws-s3-216':'Waveshare 2.16',
});
export function firmwareForBoard(board) {
  // No fallback between boards that happen to use the same ESP32-S3 chipset.
  return board === 'ws-s3-175c' ? firmware : null;
}
