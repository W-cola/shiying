"""Build a portable Windows app from the tested checkout."""
import shutil
import os
import subprocess
import sys
import ssl
import imageio_ffmpeg
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
subprocess.run([str(Path(sys.executable).with_name("pyside6-rcc.exe")), str(root / "assets" / "theme.qrc"),
                "-o", str(root / "clipharbor" / "_resources.py")], check=True)
from PySide6.QtWidgets import QApplication
from clipharbor.icons import export_icons
app = QApplication([])
icon_dir = root / "assets"
icon_dir.mkdir(exist_ok=True)
export_icons(icon_dir)
icon = icon_dir / "app.ico"
clean_flags = ["--clean"] if "--clean" in sys.argv[1:] else []
subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", *clean_flags, "--windowed",
                "--onedir", "--distpath", str(root / "build" / "desktop-dist"),
                "--name", "ShiYing", "--icon", str(icon), "--collect-all", "playwright",
                "--version-file", str(icon_dir / "windows-version.txt"),
                "--add-data", str(root / "clipharbor" / "browser_read.js") + ";clipharbor",
                "--add-data", str(root / "clipharbor" / "browser_capture.js") + ";clipharbor",
                "--add-data", str(root / "assets" / "speech") + ";assets/speech",
                "--collect-all", "sherpa_onnx",
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
shutil.copy2(icon, output / "拾影.ico")
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
