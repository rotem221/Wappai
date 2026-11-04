#!/usr/bin/env python3
"""Wappai Hub launcher: source-based desktop control on macOS, Windows and Linux.
No elevated installer, embedded VPN credentials, public tunnel or silent firewall changes.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
STATE=Path(os.environ.get('WAPPAI_HOME',Path.home()/'.wappai'))
PYTHON=STATE/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')

def environment():
    STATE.mkdir(parents=True,exist_ok=True)
    if os.name!='nt':STATE.chmod(0o700)
    envfile=STATE/'hub.env'
    if not envfile.exists():
        envfile.write_text('DEVICE_TOKEN='+secrets.token_hex(32)+'\nDATA_DIR='+str(STATE/'data')+'\nHOST=0.0.0.0\nPORT=8770\nSTT_ENGINE=whisper\nSTT_LANGUAGE=auto\nBRAIN=claude_cli\nMEETING_QUOTA_MB=4096\n',encoding='utf-8')
        if os.name!='nt':envfile.chmod(0o600)
    return {**os.environ,'COMPANION_ENV':str(envfile),'PYTHONPATH':str(ROOT/'server')}

def doctor():
    return {'python':sys.version.split()[0],'python_supported':sys.version_info>=(3,11),'ffmpeg':bool(shutil.which('ffmpeg')),'tailscale':bool(shutil.which('tailscale')),'claude':bool(shutil.which('claude')),'codex':bool(shutil.which('codex')),'hub_installed':PYTHON.is_file(),'platform':sys.platform}

def check_port_available(port=8770):
    with socket.socket() as probe:
        try:probe.bind(('0.0.0.0',port))
        except OSError as exc:
            raise RuntimeError(f'Port {port} is already in use. Stop the existing server before starting this Hub.') from exc

def wait_for_hub(process,timeout=45):
    """A child process existing is not proof that imports/startup succeeded."""
    deadline=time.monotonic()+timeout
    # The local readiness probe must not go through an inherited HTTP proxy.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic()<deadline:
        code=process.poll()
        if code is not None:
            raise RuntimeError(f'Hub exited during startup (code {code}). See {STATE / "hub.log"}.')
        try:
            with opener.open('http://127.0.0.1:8770/api/health',timeout=2) as response:
                health=json.load(response)
            if isinstance(health,dict) and health.get('ok') is True and isinstance(health.get('devices'),list):
                return
        except (OSError,ValueError,urllib.error.URLError):pass
        time.sleep(.25)
    raise RuntimeError(f'Hub did not become ready. See {STATE / "hub.log"}.')

def stop_process(process):
    if process and process.poll() is None:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=5)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--doctor',action='store_true');args=parser.parse_args()
    if args.doctor:print(json.dumps(doctor(),indent=2));return
    import tkinter as tk
    from tkinter import ttk,messagebox
    env=environment();child=None
    app=tk.Tk();app.title('Wappai Hub');app.geometry('680x540')
    brand_path=ROOT/'assets'/'brand'/'wappai-hub-wordmark.png'
    if brand_path.is_file():
        app.brand_image=tk.PhotoImage(file=str(brand_path))
        ttk.Label(app,image=app.brand_image).pack(pady=(18,4))
        ttk.Label(app,text='Hub',font=('',14,'bold')).pack(pady=(0,10))
    else:
        ttk.Label(app,text='Wappai Hub',font=('',26,'bold')).pack(pady=18)
    ttk.Label(app,text='Your computer is your Hub. Keep it running for remote access.').pack()
    status=tk.StringVar(value='Ready — run Check setup first.');ttk.Label(app,textvariable=status,wraplength=620).pack(pady=12)
    output=tk.Text(app,height=15,wrap='word');output.pack(fill='both',expand=True,padx=18,pady=10)
    def write(text):app.after(0,lambda:(output.insert('end',text+'\n'),output.see('end')))
    busy=False
    def background(action):
        nonlocal busy
        if busy:return
        busy=True
        def job():
            nonlocal busy
            try:action()
            except Exception as exc:
                write(str(exc));app.after(0,lambda message=str(exc):status.set(message))
            finally:busy=False
        threading.Thread(target=job,daemon=True).start()
    def run(command):
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1800)
        write(result.stdout[-10000:]);write(result.stderr[-3000:])
        if result.returncode:raise RuntimeError('Command failed; see details above.')
    def setup():
        if sys.version_info<(3,11):raise RuntimeError('Install Python 3.11 or newer from python.org.')
        if not PYTHON.exists():run([sys.executable,'-m','venv',str(STATE/'venv')])
        run([str(PYTHON),'-m','pip','install','-r',str(ROOT/'server/requirements.txt')])
        write('Hub installed. Install FFmpeg separately, then sign in to Claude Code or Codex. First transcription downloads its model.')
    def start():
        nonlocal child
        if child and child.poll() is None:write('Already running.');return
        if not PYTHON.exists():raise RuntimeError('Choose Install Hub first.')
        if not shutil.which('ffmpeg'):raise RuntimeError('FFmpeg is missing. Follow the setup guide.')
        check_port_available()
        app.after(0,lambda:status.set('Starting Hub… checking readiness.'))
        with (STATE/'hub.log').open('ab') as log:
            if os.name!='nt':os.chmod(log.name,0o600)
            child=subprocess.Popen([str(PYTHON),'-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8770'],cwd=ROOT/'server',env=env,stdout=log,stderr=log)
        try:wait_for_hub(child)
        except Exception:
            stop_process(child);child=None;raise
        app.after(0,lambda:status.set('Hub ready. Local network access requires your firewall permission.'))
    def stop():
        nonlocal child
        stop_process(child)
        child=None;app.after(0,lambda:status.set('Hub stopped. Remote requests and notifications are unavailable.'))
    def pair():run([str(PYTHON),'-c','from app import admin; print("One-time app pairing code:",admin.new_code(pair=True)); print("Browser sign-in code:",admin.new_code())'])
    def tailscale():
        if not shutil.which('tailscale'):webbrowser.open('https://tailscale.com/download');return
        result=subprocess.run(['tailscale','status','--json'],capture_output=True,text=True,timeout=15)
        if result.returncode or json.loads(result.stdout).get('BackendState')!='Running':raise RuntimeError('Open Tailscale and sign in, then try again.')
        # Private tailnet only. Never enable Funnel or disable TLS verification.
        run(['tailscale','serve','--bg','http://127.0.0.1:8770'])
        write('Private HTTPS enabled for your tailnet. Install/sign in to Tailscale on the phone too. ESP32 uses the LAN address, not the tailnet address.')
    buttons=ttk.Frame(app);buttons.pack(padx=18,pady=8)
    for i,(label,action) in enumerate([('Check setup',lambda:write(json.dumps(doctor(),indent=2))),('Install Hub',setup),('Start',start),('Stop',stop),('Pair app',pair),('Remote access',tailscale)]):ttk.Button(buttons,text=label,command=lambda f=action:background(f)).grid(row=i//3,column=i%3,padx=5,pady=5)
    ttk.Button(app,text='Open Wappai',command=lambda:webbrowser.open('http://localhost:8770')).pack(pady=5)
    ttk.Button(app,text='Setup guide',command=lambda:webbrowser.open('https://github.com/rotem221/Wappai/blob/main/docs/END_USER_GUIDE.he.md')).pack()
    def close():
        if child and child.poll() is None:
            if not messagebox.askokcancel('Stop Hub?','Closing stops the Hub and remote access.'):return
            stop()
        app.destroy()
    app.protocol('WM_DELETE_WINDOW',close);app.mainloop()

if __name__=='__main__':main()
