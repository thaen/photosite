#!/usr/bin/env python3
"""Install only this app's independent report worker; never alter its web service."""
import os
from pathlib import Path
import plistlib
import subprocess
from report_config import inbox

root = Path(__file__).resolve().parent
label = 'com.ethanjohn.' + inbox.app.replace('-', '') + '-reports'
plist = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
log = inbox.directory / 'worker.log'
reports_variable = {'adhd-log':'ADHD_LOG_REPORTS_DIR', 'family-video':'FAMILY_VIDEO_REPORTS_DIR'}.get(inbox.app)
with inbox.database():
    pass
configuration = {
    'Label': label,
    'ProgramArguments': ['/usr/bin/caffeinate', '-s', '/usr/bin/python3', str(root / 'report_worker.py')],
    'WorkingDirectory': str(Path.home() / 'brain'),
    'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10,
    'EnvironmentVariables': {'PYTHONUNBUFFERED': '1', **({reports_variable: str(inbox.directory)} if reports_variable else {})},
    'StandardOutPath': str(log), 'StandardErrorPath': str(log),
}
if plist.exists():
    plist.with_suffix('.plist.previous').write_bytes(plist.read_bytes())
subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{label}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
plist.write_bytes(plistlib.dumps(configuration))
subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(plist)], check=True)
print(f'Installed {label}')
