"""Build a portable Windows app from the tested checkout."""
import shutil
import os
import struct
import subprocess
import sys
import ssl
import imageio_ffmpeg
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
                "--onedir", "--distpath", str(root / "build" / "desktop-dist"),
                "--name", "ShiYing", "--icon", str(icon), "--collect-all", "playwright",
                "--collect-all", "imageio_ffmpeg",
                "--collect-all", "yt_dlp", "--exclude-module", "PySide6.QtWebEngineCore",
                "--exclude-module", "PySide6.QtWebEngineWidgets", "--exclude-module", "pytest",
                "--exclude-module", "tkinter", str(root / "main.py")], cwd=root, check=True)
output = root / "build" / "desktop-dist" / "ShiYing"
(output / "ShiYing.exe").rename(output / "拾影.exe")
from qt_runtime import prepare_runtime
prepare_runtime(output)
# This interpreter's ssl.py may ship a public CA-rejection list. Preserve its
# normal TLS checks in frozen builds by carrying the required data alongside it.
ssl_data = Path(ssl.__file__).with_name("codex-rejected-cas.pem")
if ssl_data.is_file():
    shutil.copy2(ssl_data, output / "_internal" / ssl_data.name)
shutil.copy2(root / "README.md", output / "使用说明.md")
shutil.copy2(root / "THIRD_PARTY.md", output / "第三方组件说明.md")
license_dir = output / "licenses"
license_dir.mkdir(exist_ok=True)
if (root / "assets" / "licenses").exists():
    shutil.copytree(root / "assets" / "licenses", license_dir, dirs_exist_ok=True)
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
ffmpeg_notice = subprocess.check_output([imageio_ffmpeg.get_ffmpeg_exe(), "-L"], stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
(license_dir / "FFmpeg-notice.txt").write_text(ffmpeg_notice + "\nFFmpeg source: https://github.com/FFmpeg/FFmpeg/tree/n7.1\nBinary builds: https://github.com/imageio/imageio-binaries\nGPLv3: https://www.gnu.org/licenses/gpl-3.0.txt\n", encoding="utf-8")
print("Ready:", output / "拾影.exe")
print("Staged build only. Run tools/install_desktop.py after closing the previous desktop app.")
