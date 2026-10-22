"""Opt-in live smoke test. Reports contain no media URLs, cookies or headers."""
import concurrent.futures
import json
import sys
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clipharbor.engine import Engine, safe_message
from clipharbor.media import image_extension, run_ffmpeg
from clipharbor.models import SavedMedia

root = Path('.tmp/desktop-live').resolve()
root.mkdir(parents=True, exist_ok=True)
samples = {
    'douyin': 'https://v.douyin.com/xP--46iFdBs/',
    'bilibili': 'https://www.bilibili.com/video/BV1GJ411x7h7',
    'kuaishou_album': 'https://v.kuaishou.com/njS1JbGL',
    'channels': 'https://weixin.qq.com/sph/A3loS34sJs',
}


def verify(pair):
    name, url = pair
    report = {'sample': name}
    engine = Engine(root/name/'data')
    try:
        info = engine.resolve(url)
        result = engine.download(info, info.formats[0], root/name/'files')
        files = result.files if isinstance(result, SavedMedia) else [result]
        if info.kind == 'images':
            for path in files:
                if path.suffix != '.txt':
                    image_extension(path)
        else:
            run_ffmpeg(['-i', result, '-f', 'null', '-'], Event())
            audio = engine.extract_audio(info, info.formats[0], root/name/'audio', result)
            run_ffmpeg(['-i', audio.path, '-f', 'null', '-'], Event())
            report['audio_bytes'] = audio.path.stat().st_size
        report.update(ok=True, platform=info.platform, kind=info.kind, id=info.video_id, title=info.title,
                      formats=len(info.formats), images=len(info.images), bytes=sum(p.stat().st_size for p in files),
                      validated='image headers and all files' if info.kind == 'images' else 'complete audio/video decode and extracted audio decode')
    except Exception as error:
        report.update(ok=False, error=safe_message(error))
    return report


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    reports = list(executor.map(verify, samples.items()))
(root/'report.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(reports, ensure_ascii=False, indent=2))
