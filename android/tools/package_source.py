import hashlib
import json
import zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[2]
source=root/'android'
archive=root/'dist'/'拾影-安卓版-源码.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
    for path in sorted(source.rglob('*')):
        if not path.is_file() or any(part in ('build','.gradle','__pycache__') for part in path.relative_to(source).parts): continue
        if path.suffix in ('.mp4','.jks','.keystore','.log') or path.name in ('local.properties','runtime-log.txt','ui-last.xml','browser.png','mobile-browser.png'): continue
        bundle.write(path,Path('拾影-安卓源码')/path.relative_to(source))
with zipfile.ZipFile(archive) as bundle: assert bundle.testzip() is None
apk=root/'dist'/'拾影-安卓版-v1.7.0.apk'
with zipfile.ZipFile(apk) as bundle:
    assert bundle.testzip() is None
    assert {'AndroidManifest.xml','classes.dex','resources.arsc'} <= set(bundle.namelist())
    assert not any(name.endswith(('.jks','.keystore')) for name in bundle.namelist())
print(json.dumps({'apk':str(apk),'bytes':apk.stat().st_size,'sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),
                  'source_archive':str(archive),'source_bytes':archive.stat().st_size},ensure_ascii=False))
