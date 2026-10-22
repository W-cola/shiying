"""Package only deliverable files; never include browser sessions or test data."""
import json
import shutil
import sys
import zipfile
from importlib.metadata import distributions
from pathlib import Path

root = Path(__file__).resolve().parent.parent
output = root / "dist" / "ShiYing"
assert (output / "拾影.exe").is_file(), "Build the app first"
from qt_runtime import prepare_runtime
prepare_runtime(output)
readme = (root / "README.md").read_text(encoding="utf-8")
readme = readme.replace("双击项目中的 `启动拾影.cmd`，或 `dist/ShiYing/拾影.exe`。", "双击解压后文件夹中的 `拾影.exe`。")
(output / "使用说明.md").write_text(readme, encoding="utf-8")
shutil.copy2(root / "THIRD_PARTY.md", output / "第三方组件说明.md")
license_dir = output / "licenses"
license_dir.mkdir(exist_ok=True)
if (root / "assets" / "licenses").exists():
    shutil.copytree(root / "assets" / "licenses", license_dir, dirs_exist_ok=True)
for distribution in distributions():
    name = distribution.metadata.get("Name", "unknown")
    for file in distribution.files or []:
        if any(part.lower().startswith(("license", "copying", "notice")) for part in file.parts):
            source = Path(distribution.locate_file(file))
            if source.is_file():
                dest = license_dir / name / str(file).replace("/", "_").replace("\\", "_")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    shutil.copy2(python_license, license_dir / "Python-LICENSE.txt")

portable = root / "dist" / "拾影-便携版.zip"
with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for file in sorted(output.rglob("*")):
        relative = file.relative_to(output)
        if file.is_file() and relative.parts[0] not in ("data", "downloads"):
            archive.write(file, Path("拾影") / relative)
source_zip = root / "dist" / "拾影-源码.zip"
sources = [root / name for name in ("main.py", "README.md", "THIRD_PARTY.md", ".gitignore", "启动拾影.cmd", "requirements.txt", "requirements-dev.txt", "requirements-lock.txt")]
sources.append(root / "pytest.ini")
for directory, pattern in (("clipharbor", "*.py"), ("tests", "*.py"), ("tools", "*.py"), ("assets", "*"), ("docs", "*.md")):
    sources.extend((root / directory).rglob(pattern))
with zipfile.ZipFile(source_zip, "w", zipfile.ZIP_DEFLATED) as archive:
    for file in sorted(set(sources)):
        if file.is_file():
            archive.write(file, Path("拾影-源码") / file.relative_to(root))
print(json.dumps({"portable": str(portable), "bytes": portable.stat().st_size,
                  "source": str(source_zip)}, ensure_ascii=False))
