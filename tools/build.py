"""Build a portable Windows app from the tested checkout."""
import shutil
import os
import struct
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from clipharbor.gui import app_icon
app = QApplication([])
icon_dir = root / "assets"
icon_dir.mkdir(exist_ok=True)
png = icon_dir / "app.png"
app_icon().pixmap(128, 128).save(str(png))
image = png.read_bytes()
icon = icon_dir / "app.ico"
icon.write_bytes(struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', 128, 128, 0, 0, 1, 32, len(image), 22) + image)
subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
                "--onedir", "--name", "ShiYing", "--icon", str(icon), "--collect-all", "playwright",
                "--collect-all", "yt_dlp", "--exclude-module", "PySide6.QtWebEngineCore",
                "--exclude-module", "PySide6.QtWebEngineWidgets", "--exclude-module", "pytest",
                "--exclude-module", "tkinter", str(root / "main.py")], cwd=root, check=True)
output = root / "dist" / "ShiYing"
(output / "ShiYing.exe").rename(output / "拾影.exe")
from qt_runtime import prepare_runtime
prepare_runtime(output)
shutil.copy2(root / "README.md", output / "使用说明.md")
shutil.copy2(root / "THIRD_PARTY.md", output / "第三方组件说明.md")
license_dir = output / "licenses"
license_dir.mkdir(exist_ok=True)
from importlib.metadata import distributions
for distribution in distributions():
    name = distribution.metadata.get("Name", "unknown")
    for file in distribution.files or []:
        if any(part.lower().startswith(('license', 'copying', 'notice')) for part in file.parts):
            source = Path(distribution.locate_file(file))
            if source.is_file():
                dest = license_dir / name / str(file).replace('/', '_').replace('\\', '_')
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    shutil.copy2(python_license, license_dir / "Python-LICENSE.txt")
print("Ready:", output / "拾影.exe")
