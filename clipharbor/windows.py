"""Windows window/taskbar identity, independent of shortcut icon caches."""
import ctypes
import sys
import uuid
from pathlib import Path

APP_ID = "cn.shiying.desktop"
_icons = {}


class GUID(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16), ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte*8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", ctypes.c_uint32)]


class Value(ctypes.Union):
    _fields_ = [("text", ctypes.c_wchar_p), ("storage", ctypes.c_byte*16)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("reserved1", ctypes.c_ushort), ("reserved2", ctypes.c_ushort),
                ("reserved3", ctypes.c_ushort), ("value", Value)]


def property_store(hwnd):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.SHGetPropertyStoreForWindow.argtypes = [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetPropertyStoreForWindow.restype = ctypes.c_long
    store = ctypes.c_void_p()
    iid = GUID.parse("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")
    result = shell.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid), ctypes.byref(store))
    if result < 0:
        raise OSError(f"Window property store failed: {result:#x}")
    return store


def method(store, index, result, *args):
    table = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *args)(table[index])


def key(pid):
    return PROPERTYKEY(GUID.parse("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"), pid)


def window_properties(hwnd, values=None):
    store = property_store(hwnd)
    try:
        if values is not None:
            setter = method(store, 6, ctypes.c_long, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))
            # Relaunch properties precede ID: setting ID asks the taskbar to refresh.
            for pid, text in values:
                value = PROPVARIANT()
                value.vt = 31  # VT_LPWSTR; IPropertyStore copies the string.
                value.value.text = text
                result = setter(store, ctypes.byref(key(pid)), ctypes.byref(value))
                if result < 0:
                    raise OSError(f"Window identity property {pid} failed: {result:#x}")
        getter = method(store, 5, ctypes.c_long, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))
        result = {}
        for pid, name in ((2, "relaunch_command"), (3, "icon_resource"), (4, "display_name"), (5, "app_id")):
            value = PROPVARIANT()
            if getter(store, ctypes.byref(key(pid)), ctypes.byref(value)) >= 0:
                result[name] = value.value.text if value.vt == 31 else ""
                ctypes.windll.ole32.PropVariantClear(ctypes.byref(value))
        return result
    finally:
        method(store, 2, ctypes.c_ulong)(store)


def bind_window(widget):
    from PySide6.QtGui import QGuiApplication
    if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
        return {}
    from .store import app_root
    icon_file = app_root() / "拾影.ico" if getattr(sys, "frozen", False) else app_root() / "assets" / "app.ico"
    hwnd = int(widget.winId())
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user.LoadImageW.restype = ctypes.c_void_p
    user.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    user.SendMessageW.restype = ctypes.c_ssize_t
    setter = user.SetClassLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user.SetClassLongW
    setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    setter.restype = ctypes.c_ssize_t
    for kind, size, index in ((0, 32, -34), (1, 48, -14)):
        cache = (str(icon_file), size)
        if cache not in _icons:
            _icons[cache] = user.LoadImageW(None, str(icon_file), 1, size, size, 0x10)
        if not _icons[cache]:
            raise OSError("无法加载拾影 Windows 图标")
        user.SendMessageW(hwnd, 0x80, kind, _icons[cache])  # WM_SETICON
        setter(hwnd, index, _icons[cache])
    executable = Path(sys.executable).resolve()
    command = f'"{executable}"' if getattr(sys, "frozen", False) else f'"{executable}" "{app_root() / "main.py"}"'
    return window_properties(hwnd, [(2, command), (3, str(icon_file)+",0"), (4, "拾影"), (5, APP_ID)])


def diagnose_window(widget):
    """Read back this app's real Win32 icon handles and shell identity for QA."""
    from PySide6.QtGui import QGuiApplication
    if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
        return {"native": False}
    hwnd = int(widget.winId())
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    user.SendMessageW.restype = ctypes.c_ssize_t
    handles = {name: user.SendMessageW(hwnd, 0x7f, kind, 0) for name, kind in (("small", 0), ("large", 1))}
    expected = set(_icons.values())
    return {"native": True, "hwnd": hwnd, "icons": handles,
            "icons_match_loaded_ico": all(h and h in expected for h in handles.values()),
            **window_properties(hwnd), "qt_icon_sizes": [s.width() for s in widget.windowIcon().availableSizes()]}
