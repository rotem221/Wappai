import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {verifyFirmware} from '../flash-integrity.js';
import {firmware, publicAppStoreUrl} from '../release-config.js';
const image = await readFile(new URL('../firmware/Wappai-1.75C-factory.bin',import.meta.url));
const arrayBuffer = data => Uint8Array.from(data).buffer;
test('shipped factory image matches release hash and ESP32-S3 header',async()=>{
  assert.equal(await verifyFirmware(arrayBuffer(image),firmware),firmware.sha256);
});
test('truncated firmware is rejected',async()=>{
  await assert.rejects(verifyFirmware(arrayBuffer(image.subarray(0,-1)),firmware),/size mismatch/);
});
test('modified firmware is rejected before USB access',async()=>{
  const corrupt=Uint8Array.from(image);corrupt[100000]^=1;
  await assert.rejects(verifyFirmware(corrupt.buffer,firmware),/checksum mismatch/);
});
test('an image for a different ESP chip is rejected',async()=>{
  const wrong=Uint8Array.from(image);wrong[12]=0;
  await assert.rejects(verifyFirmware(wrong.buffer,firmware),/Not an ESP32-S3/);
});
test('unpublished App Store status never fabricates a store destination',()=>{
  assert.equal(publicAppStoreUrl(),null);
  for(const url of ['https://apps.apple.com/search?term=wappai','https://example.com/id123456','javascript:alert(1)','http://apps.apple.com/app/id123456','https://apps.apple.com.evil.test/id123456'])assert.equal(publicAppStoreUrl(url),null);
  assert.equal(publicAppStoreUrl('https://apps.apple.com/il/app/wappai/id1234567890'),'https://apps.apple.com/il/app/wappai/id1234567890');
});
test('browser manifest is limited to the validated board and prompts before erase',async()=>{
  const manifest=JSON.parse(await readFile(new URL('../firmware/manifest.json',import.meta.url)));
  assert.equal(manifest.new_install_prompt_erase,true);
  assert.equal(manifest.new_install_improv_wait_time,0);
  assert.equal(manifest.builds.length,1);
  assert.equal(manifest.builds[0].chipFamily,'ESP32-S3');
  assert.deepEqual(manifest.builds[0].parts,[{path:'Wappai-1.75C-factory.bin',offset:0}]);
});
