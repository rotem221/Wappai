"""Launcher readiness must not claim success for a failed/background process."""
import importlib.util
import io
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

spec=importlib.util.spec_from_file_location('wappai_launcher',Path(__file__).resolve().parents[2]/'desktop/wappai_hub.py')
launcher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_occupied_port_is_reported_without_touching_listener():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen()
        with pytest.raises(RuntimeError,match='already in use'):
            launcher.check_port_available(listener.getsockname()[1])
        assert listener.fileno()>=0


def test_failed_process_never_reports_ready():
    with pytest.raises(RuntimeError,match='code 1'):
        launcher.wait_for_hub(SimpleNamespace(poll=lambda:1))


def test_readiness_waits_through_startup_and_rejects_unrelated_response(monkeypatch):
    responses=[OSError('starting'),b'{"ok":true}',b'{"ok":true,"devices":[]}'];calls=[]
    def open_health(url,timeout):
        calls.append(url);result=responses.pop(0)
        if isinstance(result,Exception):raise result
        return io.BytesIO(result)
    def opener(proxy):
        assert proxy.proxies=={}
        return SimpleNamespace(open=open_health)
    monkeypatch.setattr(launcher.urllib.request,'build_opener',opener)
    monkeypatch.setattr(launcher.time,'sleep',lambda _:None)
    launcher.wait_for_hub(SimpleNamespace(poll=lambda:None))
    assert len(calls)==3


def test_timeout_and_unresponsive_child_cleanup(monkeypatch):
    with pytest.raises(RuntimeError,match='did not become ready'):
        launcher.wait_for_hub(SimpleNamespace(poll=lambda:None),timeout=0)
    actions=[]
    def wait(timeout):
        actions.append(('wait',timeout))
        if timeout==15:raise subprocess.TimeoutExpired('test',timeout)
    child=SimpleNamespace(poll=lambda:None,terminate=lambda:actions.append('terminate'),
                          kill=lambda:actions.append('kill'),wait=wait)
    launcher.stop_process(child)
    assert actions==['terminate',('wait',15),'kill',('wait',5)]
