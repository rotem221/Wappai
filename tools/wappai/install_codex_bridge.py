"""Install a loopback-only Codex bridge on your Mac, without remote-host assumptions."""
import argparse, os, plistlib, secrets, shutil, subprocess, sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=sys.executable, help='Python with fastapi and uvicorn installed')
    parser.add_argument('--prepare-only', action='store_true', help='Write files without starting the launch agent')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('This launch-agent installer is for macOS. See docs/GETTING_STARTED.md for other hosts.')
    python = str(Path(args.python).expanduser().resolve())
    subprocess.run([python, '-c', 'import fastapi, uvicorn'], check=True)
    repo = Path(__file__).resolve().parents[2]
    root = Path.home()/'.local/share/wappai/bridge'
    package = root/'app/brain'
    package.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    for path in [root/'app/__init__.py', package/'__init__.py']:
        path.touch()
    for name in ['codex.py', 'codex_bridge.py', 'pip_images.py']:
        shutil.copy2(repo/'server/app/brain'/name, package/name)
    token = root/'token'
    if not token.exists():
        with os.fdopen(os.open(token, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as stream:
            stream.write(secrets.token_hex(32))
    token.chmod(0o600)
    agentdir = Path.home()/'Library/LaunchAgents'
    agentdir.mkdir(parents=True, exist_ok=True)
    label = 'com.dadon.wappai.codex'
    body = dict(Label=label, RunAtLoad=True, KeepAlive=True, ThrottleInterval=10,
        ProgramArguments=[python, '-m', 'uvicorn', 'app.brain.codex_bridge:app', '--host', '127.0.0.1',
                          '--port', '18773', '--no-access-log', '--app-dir', str(root)],
        EnvironmentVariables={'WAPPAI_BRIDGE_TOKEN_FILE': str(token),
                              'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(Path.home())},
        StandardOutPath=str(root/(label+'.out.log')), StandardErrorPath=str(root/(label+'.err.log')))
    path = agentdir/(label+'.plist')
    path.write_bytes(plistlib.dumps(body))
    if not args.prepare_only:
        subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}', str(path)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(path)], check=True)
    print('Bridge prepared at 127.0.0.1:18773. Token file:', token)
    print('Set WAPPAI_CODEX_BRIDGE_TOKEN in your Hub environment to this private file content.')
    print('For a remote Hub, use your own loopback-only SSH tunnel; see the guide.')

if __name__ == '__main__':
    main()
