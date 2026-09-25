"""Keep the crab's windows visible everywhere, including over full-screen apps.

macOS puts full-screen apps in their own Space; normal windows don't follow. We flag
each window (via the Objective-C runtime, no extra packages) to join every Space as a
full-screen auxiliary, at status-bar level. On Windows/Linux, Qt's stay-on-top flag
already covers borderless full-screen apps, so this is a no-op there.
"""

import ctypes
import ctypes.util
import sys

from PySide6.QtGui import QGuiApplication

# NSWindowCollectionBehavior flags
CAN_JOIN_ALL_SPACES = 1 << 0
STATIONARY = 1 << 4           # don't slide around with Mission Control
IGNORES_CYCLE = 1 << 6        # skip in Cmd+` window cycling
FULL_SCREEN_AUXILIARY = 1 << 8
STATUS_WINDOW_LEVEL = 25      # above normal and floating windows

_objc = None


def _runtime():
    global _objc
    if _objc is None:
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        lib.sel_registerName.restype = ctypes.c_void_p
        lib.sel_registerName.argtypes = [ctypes.c_char_p]
        address = ctypes.cast(lib.objc_msgSend, ctypes.c_void_p).value
        # objc_msgSend must be called through an exact prototype (required on Apple Silicon).
        _objc = {
            "sel": lambda name: lib.sel_registerName(name.encode()),
            "get_id": ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(address),
            "get_ulong": ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)(address),
            "set_ulong": ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)(address),
            "set_long": ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)(address),
        }
    return _objc


def _ns_window(widget):
    rt = _runtime()
    view = int(widget.winId())  # Qt gives the NSView
    return rt["get_id"](view, rt["sel"]("window")) if view else None


def show_everywhere(widget):
    """Call after the widget is shown. Safe to call repeatedly."""
    # Only real Cocoa windows have an NSView behind winId() (not the offscreen test platform).
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return
    try:
        window = _ns_window(widget)
        if not window:
            return
        rt = _runtime()
        behavior = CAN_JOIN_ALL_SPACES | STATIONARY | IGNORES_CYCLE | FULL_SCREEN_AUXILIARY
        rt["set_ulong"](window, rt["sel"]("setCollectionBehavior:"), behavior)
        rt["set_long"](window, rt["sel"]("setLevel:"), STATUS_WINDOW_LEVEL)
    except (OSError, AttributeError, TypeError) as err:
        print(f"couldn't float window over full-screen apps: {err}", file=sys.stderr)


def collection_behavior(widget):
    """For tests: the window's current NSWindowCollectionBehavior bits."""
    rt = _runtime()
    return rt["get_ulong"](_ns_window(widget), rt["sel"]("collectionBehavior"))
