import argparse
import json
import os
import sys
import traceback
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="拾影 · 视频解析与下载")
    parser.add_argument("--url", help="使用命令行解析分享文字或视频链接")
    parser.add_argument("--download", action="store_true", help="下载第一个可用画质")
    parser.add_argument("--browser", action="store_true", help="打开浏览器手动完成登录或验证")
    parser.add_argument("--output", type=Path, help="下载目录")
    parser.add_argument("--report", type=Path, help="将命令行测试结果保存为 JSON")
    parser.add_argument("--verify-ui", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.verify_ui:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFontDatabase, QFont
        from clipharbor.gui import Window, STYLE
        app = QApplication([])
        for font in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf"):
            QFontDatabase.addApplicationFont(font)
        app.setFont(QFont("Microsoft YaHei", 10))
        app.setStyle("Fusion")
        app.setStyleSheet(STYLE)
        window = Window()
        window.resize(1120, 1040)
        window.show()
        app.processEvents()
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            screenshot = args.report.with_suffix(".png")
            if not window.grab().save(str(screenshot)):
                raise RuntimeError("Unable to render UI")
            args.report.write_text(json.dumps({"ok": True, "title": window.windowTitle(),
                                  "screenshot": str(screenshot)}, ensure_ascii=False), encoding="utf-8")
        window.close()
        app.processEvents()
        return 0
    if args.url:
        from clipharbor.engine import Engine
        from clipharbor.store import Store
        store = Store()
        engine = Engine(store.root, lambda s: print(s, flush=True))
        try:
            info = engine.resolve(args.url, args.browser)
            report = {"id": info.video_id, "title": info.title, "author": info.author,
                              "duration": info.duration, "engine": info.engine,
                              "formats": [{"label": f.label, "size": f.size} for f in info.formats]}
            print(json.dumps(report, ensure_ascii=False))
            if args.download:
                path = engine.download(info, info.formats[0], args.output or Path(store.settings["download_dir"]))
                store.add_history(info, path)
                print("保存到：" + str(path))
                report["file"] = str(path)
                report["bytes"] = path.stat().st_size
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return 0
        except Exception as error:
            from clipharbor.engine import safe_message
            print(safe_message(error), file=sys.stderr)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps({"error": safe_message(error)}, ensure_ascii=False), encoding="utf-8")
            return 1
    from clipharbor.gui import run
    return run()


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as error:
        from clipharbor.store import app_root
        log_root = Path(os.environ.get("CLIPHARBOR_DATA", str(app_root() / "data")))
        try:
            log_root.mkdir(parents=True, exist_ok=True)
            (log_root / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
            if "--report" in sys.argv:
                report_path = Path(sys.argv[sys.argv.index("--report") + 1])
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps({"ok": False, "error": traceback.format_exc()}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        if sys.stderr:
            traceback.print_exc()
        if "--url" not in sys.argv and "--verify-ui" not in sys.argv:
            try:
                from PySide6.QtWidgets import QApplication, QMessageBox
                app = QApplication.instance() or QApplication([])
                QMessageBox.critical(None, "拾影启动失败", f"无法启动应用：{error}\n\n详细信息：{log_root / 'startup-error.log'}")
            except Exception:
                pass
        exit_code = 1
    raise SystemExit(exit_code)
