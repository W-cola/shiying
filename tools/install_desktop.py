"""Install a tested staged build while preserving all portable user state."""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = root/'build'/'desktop-dist'/'ShiYing'
target = root/'dist'/'ShiYing'
if not (source/'拾影.exe').is_file():
    raise SystemExit('请先运行 tools/build.py。')
# Never delete/replace the app directory: it also holds real user data.
# copytree updates program files and leaves data/ and downloads/ untouched.
shutil.copytree(source, target, dirs_exist_ok=True)
print('Installed:', target/'拾影.exe')
