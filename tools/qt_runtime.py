"""Keep Windows Qt's native ICU dependency from being shadowed by build tools."""
from pathlib import Path
import pefile


def prepare_runtime(output: Path):
    core = output / "_internal" / "PySide6" / "Qt6Core.dll"
    collision = output / "_internal" / "icuuc.dll"
    if not core.is_file() or not collision.is_file():
        return
    qt = pefile.PE(str(core), fast_load=True)
    qt.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    native_icu = any(dep.dll.lower() == b"icuuc.dll" and
                     any(symbol.name == b"ucnv_open" for symbol in dep.imports)
                     for dep in qt.DIRECTORY_ENTRY_IMPORT)
    icu = pefile.PE(str(collision), fast_load=True)
    icu.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    exports = {s.name for s in icu.DIRECTORY_ENTRY_EXPORT.symbols}
    if native_icu and b"ucnv_open" not in exports:
        # An ICU build with suffixed exports (e.g. ucnv_open_78) is unrelated
        # to the Windows ICU shim required by this Qt build. It was picked
        # from the host Python tool runtime during DLL discovery.
        assert collision.resolve().is_relative_to(output.resolve())
        collision.unlink()
        for data in collision.parent.glob("icudt*.dll"):
            assert data.resolve().is_relative_to(output.resolve())
            data.unlink()
        print("Removed conflicting host ICU; Qt will use the Windows ICU runtime.")
