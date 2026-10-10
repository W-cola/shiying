import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

root = Path(__file__).resolve().parents[2]
tool_root = root / '.android-build'
sdk = tool_root / 'sdk'
downloads = tool_root / 'downloads'
downloads.mkdir(parents=True, exist_ok=True)
archive = downloads / 'commandlinetools-win-15859902_latest.zip'
expected = '90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a'
if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
    print('Downloading official Android SDK command-line tools...', flush=True)
    with requests.get('https://dl.google.com/android/repository/' + archive.name, stream=True, timeout=60) as response:
        response.raise_for_status()
        with archive.open('wb') as output:
            for chunk in response.iter_content(1024 * 1024):
                output.write(chunk)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected, 'SDK checksum mismatch'
latest = sdk / 'cmdline-tools' / 'latest'
if not (latest / 'bin' / 'sdkmanager.bat').exists():
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            path = Path(item.filename)
            if path.parts[0] != 'cmdline-tools':
                continue
            dest = latest.joinpath(*path.parts[1:])
            assert dest.resolve().is_relative_to(latest.resolve())
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(bundle.read(item))
java = Path(os.environ.get('SHIYING_JDK', 'D:/PyCharm 2026.1.1/jbr'))
env = os.environ.copy()
env.update(JAVA_HOME=str(java), ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk),
           ANDROID_USER_HOME=str(tool_root / 'android-user'), TEMP=str(root / '.tmp'), TMP=str(root / '.tmp'))
sdkmanager = latest / 'bin' / 'sdkmanager.bat'
proxy = requests.utils.urlparse(os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or '')
proxy_args = ['--proxy=http', '--proxy_host=' + proxy.hostname, '--proxy_port=' + str(proxy.port)] if proxy.hostname else []
subprocess.run([str(sdkmanager), '--sdk_root=' + str(sdk), *proxy_args, '--licenses'],
               input='y\n' * 100, text=True, env=env, check=True)
packages = sys.argv[1:] or ['platform-tools', 'platforms;android-35', 'build-tools;35.0.1']
subprocess.run([str(sdkmanager), '--sdk_root=' + str(sdk), *proxy_args, *packages], env=env, check=True)
print('SDK ready:', sdk, flush=True)
