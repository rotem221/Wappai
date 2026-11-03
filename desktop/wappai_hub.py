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
import subprocess
import sys
import threading
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

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--doctor',action='store_true');args=parser.parse_args()
    if args.doctor:print(json.dumps(doctor(),indent=2));return
    import tkinter as tk
    from tkinter import ttk,messagebox
    env=environment();child=None
    app=tk.Tk();app.title('Wappai Hub');app.geometry('680x540')
    title=ttk.Label(app,text='Wappai Hub',font=('',26,'bold'));title.pack(pady=18)
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
            except Exception as exc:write(str(exc))
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
        log=(STATE/'hub.log').open('ab')
        child=subprocess.Popen([str(PYTHON),'-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8770'],cwd=ROOT/'server',env=env,stdout=log,stderr=log);log.close()
        app.after(0,lambda:status.set('Hub running. Local network access requires your firewall permission.'))
    def stop():
        nonlocal child
        if child and child.poll() is None:child.terminate();child.wait(timeout=15)
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
