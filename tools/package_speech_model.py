"""Create the same validated offline model ZIP accepted by phone and desktop."""
import argparse
import json
import sys
import zipfile
from pathlib import Path
from threading import Event

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from clipharbor.speech_models import SpeechModels

parser = argparse.ArgumentParser()
parser.add_argument("--models", required=True, type=Path)
parser.add_argument("--output", type=Path, default=root/"dist/拾影-中文离线识别包.zip")
args = parser.parse_args()
models = SpeechModels(root/".tmp/package-model-check")
for item in models.files:
    if not models.verify(args.models/item["name"], item, Event()):
        raise SystemExit("模型校验失败："+item["name"])
args.output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for item in models.files:
        archive.write(args.models/item["name"], item["name"])
    archive.writestr("speech-model.json", json.dumps(models.manifest, ensure_ascii=False, indent=2))
print(args.output)
