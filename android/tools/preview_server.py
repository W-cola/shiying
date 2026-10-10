"""Loopback-only interactive screen bridge to this project's isolated Android emulator.

No production APK debug endpoints, third-party web assets or arbitrary shell execution.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shlex
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(os.environ.get('SHIYING_BUILD_ROOT', str(Path(__file__).resolve().parents[2])))
SDK = ROOT / '.android-build/sdk'
ADB = SDK / 'platform-tools/adb.exe'
SERIAL = 'emulator-5580'
ADB_PORT = '5039'
PORT = 8787
ENV = os.environ.copy()
ENV.update(ANDROID_HOME=str(SDK), ANDROID_SDK_ROOT=str(SDK),
           ANDROID_USER_HOME=str(ROOT / '.android-build/android-user'),
           ANDROID_AVD_HOME=str(ROOT / '.android-build/avd'),
           ANDROID_ADB_SERVER_PORT=ADB_PORT, ADB_SERVER_PORT=ADB_PORT,
           TEMP=str(ROOT / '.tmp'), TMP=str(ROOT / '.tmp'), PYTHONUTF8='1')
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
TOKEN = secrets.token_urlsafe(32)
state = {'ready': False, 'busy': True, 'status': '正在连接安卓模拟器…', 'version': '', 'width': 1080, 'height': 2400}
state_lock = threading.Lock()
screen_lock = threading.Lock()
action_lock = threading.Lock()
screen = b''
screen_time = 0.0


def adb(*args, timeout=30):
    result = subprocess.run([str(ADB), '-P', ADB_PORT, '-s', SERIAL, *map(str, args)],
                            env=ENV, capture_output=True, timeout=timeout, creationflags=FLAGS)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', 'replace').strip()[:700] or '模拟器命令未完成')
    return result.stdout


def update(**values):
    with state_lock:
        state.update(values)


def install():
    report = json.loads((ROOT / 'android/verification/build.json').read_text(encoding='utf-8'))
    name = Path(report['apk']).name
    if not name.endswith('.apk'):
        raise RuntimeError('没有可安装的 APK')
    # SDK binaries receive an ASCII filename even if the workspace uses Chinese characters.
    import shutil
    package = ROOT / '.android-build/app-build/preview-install.apk'
    shutil.copy2(ROOT / 'dist' / name, package)
    update(status='正在覆盖安装新版 APK，保留原有数据…')
    adb('install', '-r', str(package), timeout=90)
    adb('shell', 'am', 'start', '-W', '-n', 'cn.shiying.mobile/.MainActivity')
    update(version=report['version'], status='已连接 · 点击屏幕即可操作', ready=True)


def boot():
    try:
        if not ADB.exists():
            raise RuntimeError('未找到 Android SDK，请先按 android/README.md 配置构建环境')
        try:
            online = adb('get-state', timeout=6).strip() == b'device'
        except Exception:
            online = False
        if not online:
            avd = ROOT / '.android-build/avd/shiying-test.avd'
            if not avd.is_dir():
                raise RuntimeError('未找到 shiying-test 模拟器，请先运行 create_test_device.py')
            update(status='正在启动安卓模拟器，首次启动需要稍等…')
            log = ROOT / '.tmp/preview-emulator.log'
            with log.open('ab') as output:
                subprocess.Popen([str(SDK / 'emulator/emulator.exe'), '-avd', 'shiying-test',
                                  '-port', '5580', '-no-window', '-no-boot-anim', '-no-snapshot',
                                  '-no-metrics', '-gpu', 'swiftshader', '-feature', '-Vulkan',
                                  '-memory', '3072', '-cores', '4'], cwd=ROOT, env=ENV,
                                 stdout=output, stderr=output, creationflags=FLAGS)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                if adb('shell', 'getprop', 'sys.boot_completed', timeout=5).strip() == b'1':
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('模拟器启动超时，请查看 .tmp/preview-emulator.log')
        adb('shell', 'input', 'keyevent', '224')
        adb('shell', 'wm', 'dismiss-keyguard')
        adb('shell', 'settings', 'put', 'system', 'screen_off_timeout', '2147483647')
        # Keep portrait until the APK's own full-screen button requests landscape.
        adb('shell', 'settings', 'put', 'system', 'accelerometer_rotation', '0')
        install()
    except Exception as error:
        update(status=str(error), ready=False)
    finally:
        update(busy=False)


def capture():
    global screen, screen_time
    with screen_lock:
        if time.monotonic() - screen_time >= 0.16:
            data = adb('exec-out', 'screencap', '-p', timeout=12)
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise RuntimeError('暂未收到模拟器画面')
            width, height = struct.unpack('>II', data[16:24])
            screen, screen_time = data, time.monotonic()
            update(width=width, height=height)
        return screen


def rebuild():
    try:
        result = subprocess.run([sys.executable, str(ROOT / 'android/tools/build_apk.py')],
                                cwd=ROOT, env=ENV, capture_output=True, timeout=180, creationflags=FLAGS)
        (ROOT / '.tmp/preview-build.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('编译失败，请查看 .tmp/preview-build.log；模拟器保留之前的版本')
        with action_lock:
            install()
    except Exception as error:
        update(status=str(error))
    finally:
        update(busy=False)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def allowed(self):
        return self.headers.get('Host') in (f'127.0.0.1:{PORT}', f'localhost:{PORT}')

    def send(self, data, mime='application/json; charset=utf-8', code=200):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(data)

    def json(self, value, code=200):
        self.send(json.dumps(value, ensure_ascii=False).encode('utf-8'), code=code)

    def do_GET(self):
        if not self.allowed():
            return self.json({'error': '仅供本机访问'}, 403)
        route = urlsplit(self.path).path
        try:
            if route == '/':
                page = (ROOT / 'android/tools/preview.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
                self.send(page.encode('utf-8'), 'text/html; charset=utf-8')
            elif route == '/state':
                with state_lock:
                    self.json(dict(state))
            elif route == '/screen':
                try:
                    data = capture()
                except Exception:
                    update(ready=False, status='模拟器连接中断，请点击启动 / 重新连接')
                    raise
                self.send(data, 'image/png')
            elif route == '/favicon.ico':
                self.send(b'', code=204)
            else:
                self.json({'error': '不存在的路径'}, 404)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as error:
            self.json({'error': str(error)}, 503)

    def do_POST(self):
        if not self.allowed() or self.headers.get('X-Preview-Token') != TOKEN:
            return self.json({'error': '无效的本机操作请求'}, 403)
        if self.headers.get('Origin') not in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
            return self.json({'error': '不允许跨站操作'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 2 or length > 16384:
                raise ValueError('请求过长或为空')
            value = json.loads(self.rfile.read(length))
            route = urlsplit(self.path).path
            if route == '/connect':
                with state_lock:
                    if state['busy']:
                        return self.json({'error': '正在启动或编译，请稍等'}, 409)
                    state.update(busy=True, ready=False, status='正在连接安卓模拟器…')
                threading.Thread(target=boot, daemon=True).start()
                return self.json({'ok': True})
            if route == '/stop':
                if state['busy']:
                    return self.json({'error': '正在启动或编译，请稍等'}, 409)
                with action_lock:
                    adb('emu', 'kill', timeout=10)
                    update(ready=False, status='模拟器已停止，可点击启动 / 重新连接继续测试')
                return self.json({'ok': True})
            if route == '/rebuild':
                with state_lock:
                    if state['busy']:
                        return self.json({'error': '已经在编译，请稍等'}, 409)
                    state.update(busy=True, status='正在编译新版 APK…')
                threading.Thread(target=rebuild, daemon=True).start()
                return self.json({'ok': True})
            with action_lock:
                if not state['ready']:
                    raise ValueError('模拟器尚未就绪')
                if route == '/touch':
                    width, height = state['width'], state['height']
                    def point(key, maximum):
                        return max(0, min(maximum - 1, int(float(value[key]) * maximum)))
                    x, y = point('x', width), point('y', height)
                    if 'endX' in value:
                        adb('shell', 'input', 'swipe', x, y, point('endX', width), point('endY', height), max(100, min(1000, int(value.get('duration', 250)))))
                    else:
                        adb('shell', 'input', 'tap', x, y)
                elif route == '/key':
                    keys = {'back': '4', 'home': '3', 'recent': '187', 'enter': '66', 'delete': '67', 'volume_up': '24', 'volume_down': '25'}
                    adb('shell', 'input', 'keyevent', keys[value['key']])
                elif route == '/launch':
                    adb('shell', 'am', 'start', '-W', '-n', 'cn.shiying.mobile/.MainActivity')
                elif route == '/share':
                    text = value.get('text', '')
                    if not isinstance(text, str) or not text.strip() or len(text) > 6000 or '\0' in text:
                        raise ValueError('请填写完整分享链接或分享文字（最多 6000 字）')
                    # Quote the entire Android shell command; never use a Windows shell.
                    command = 'am start -W -n cn.shiying.mobile/.MainActivity -a android.intent.action.SEND -t text/plain --es android.intent.extra.TEXT ' + shlex.quote(text)
                    adb('shell', command)
                else:
                    return self.json({'error': '不支持的操作'}, 404)
            self.json({'ok': True})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as error:
            self.json({'error': str(error)}, 400)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    PORT = args.port
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    server.daemon_threads = True
    threading.Thread(target=boot, daemon=True).start()
    print(f'Android APK preview: http://127.0.0.1:{PORT}/', flush=True)
    server.serve_forever()
