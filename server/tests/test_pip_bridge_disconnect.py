import asyncio
import importlib
import types

import pytest
from fastapi import HTTPException


def test_disconnected_image_request_cancels_worker(tmp_path, monkeypatch):
    token = tmp_path / 'bridge-token'
    token.write_text('test-only-bridge-token')
    monkeypatch.setenv('WAPPAI_BRIDGE_TOKEN_FILE', str(token))
    from app.brain import pip_images
    bridge = importlib.import_module('app.brain.codex_bridge')
    monkeypatch.setattr(bridge, 'secret', token.read_text())
    cancelled = []

    class Worker:
        async def generate(self, *args):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

    async def body(): return {'prompt': 'test character'}
    async def disconnected(): return True
    request = types.SimpleNamespace(
        headers={'authorization': 'Bearer ' + token.read_text()},
        json=body, is_disconnected=disconnected)
    monkeypatch.setattr(pip_images, 'PipImageProvider', Worker)

    async def run():
        monkeypatch.setattr(bridge, 'image_gate', asyncio.Lock())
        with pytest.raises(HTTPException) as error:
            await bridge.pip_image(request)
        assert error.value.status_code == 499
        assert error.value.detail == 'Image request disconnected'
        assert not bridge.image_gate.locked()
    asyncio.run(run())
    assert cancelled == [True]
