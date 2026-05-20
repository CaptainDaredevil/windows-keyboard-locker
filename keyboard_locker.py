import argparse
import atexit
import ctypes
from collections import deque
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback


APP_VERSION = "0.6.4"
LOCK_HOTKEY_SCAN_CODE = 38  # Physical "L" key on a standard layout.
UNLOCK_SCAN_SEQUENCE = (22, 49, 38, 24, 46, 37)  # Physical U N L O C K keys.
DEFAULT_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keyboard_locker.log")
DEFAULT_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keyboard_locker.state.json")
DEFAULT_ACCESSIBILITY_BACKUP_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "keyboard_locker.accessibility_backup.json",
)
DEFAULT_MUTEX_NAME = "Local\\KeyboardLockerByCodex"
MAX_LOG_BYTES = 1_000_000
LOG_PATH = DEFAULT_LOG_PATH
STATE_PATH = DEFAULT_STATE_PATH
ACCESSIBILITY_BACKUP_PATH = DEFAULT_ACCESSIBILITY_BACKUP_PATH
MUTEX_NAME = DEFAULT_MUTEX_NAME

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_HOTKEY = 0x0312

LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10

VK_F1 = 0x70
VK_F2 = 0x71
VK_F3 = 0x72
VK_F4 = 0x73
VK_F5 = 0x74
VK_F6 = 0x75
VK_F7 = 0x76
VK_F8 = 0x77
VK_F9 = 0x78
VK_F10 = 0x79
VK_F11 = 0x7A
VK_F12 = 0x7B
VK_Q = 0x51
VK_U = 0x55
VK_TAB = 0x09
VK_LWIN = 0x5B
VK_VOLUME_UP = 0xAF
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
MOD_NOREPEAT = 0x4000
CTRL_VKS = {VK_LCONTROL, VK_RCONTROL}
ALT_VKS = {VK_LMENU, VK_RMENU}
TOP_ROW_VKS = [VK_F1, VK_F2, VK_F3, VK_F4, VK_F5, VK_F6, VK_F7, VK_F8, VK_F9, VK_F10, VK_F11, VK_F12]
HOTKEY_ID_BASE = 1000

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = wintypes.LPARAM
HOOK_PROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else wintypes.ULONG

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOK_PROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HANDLE
user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ULONG_PTR]
user32.keybd_event.restype = None
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD
kernel32.GetCurrentProcessId.argtypes = []
kernel32.GetCurrentProcessId.restype = wintypes.DWORD


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


@dataclass(frozen=True)
class KeySnapshot:
    vk_code: int
    scan_code: int
    is_extended: bool


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"

    try:
        print(line, flush=True)
    except Exception:
        pass

    if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > MAX_LOG_BYTES:
        backup_path = LOG_PATH + ".1"
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.replace(LOG_PATH, backup_path)
        except OSError:
            pass

    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(line + "\n")


def emit_keyboard_event(vk_code: int, scan_code: int, is_keyup: bool = False, extended: bool = False) -> None:
    flags = KEYEVENTF_KEYUP if is_keyup else 0
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY

    user32.keybd_event(vk_code, scan_code & 0xFF, flags, 0)


def get_pid() -> int:
    return int(kernel32.GetCurrentProcessId())


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def write_runtime_state(payload: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    temp_path = STATE_PATH + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as state_file:
        json.dump(payload, state_file, ensure_ascii=True, indent=2)
    os.replace(temp_path, STATE_PATH)


def read_runtime_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as state_file:
            loaded = json.load(state_file)
        if isinstance(loaded, dict):
            return loaded
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def read_json_file(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            return loaded
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def write_json_file(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
    os.replace(temp_path, path)


def build_runtime_state_payload(status: str, locked: bool, pid: int | None = None) -> dict:
    return {
        "version": APP_VERSION,
        "pid": get_pid() if pid is None else pid,
        "status": status,
        "locked": locked,
        "started_at": utc_now_iso() if status == "running" else None,
        "updated_at": utc_now_iso(),
        "log_path": LOG_PATH,
        "state_path": STATE_PATH,
        "mutex_name": MUTEX_NAME,
    }


ACCESSIBILITY_REGISTRY = {
    "StickyKeys": {
        "path": r"Control Panel\Accessibility\StickyKeys",
        "values": ["Flags"],
    },
    "KeyboardResponse": {
        "path": r"Control Panel\Accessibility\Keyboard Response",
        "values": ["Flags", "AutoRepeatDelay", "AutoRepeatRate", "BounceTime"],
    },
    "ToggleKeys": {
        "path": r"Control Panel\Accessibility\ToggleKeys",
        "values": ["Flags"],
    },
}


def _normalize_registry_value(value):
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return str(value)


def _disable_accessibility_flag(flag_value: str) -> str:
    try:
        numeric = int(str(flag_value))
    except ValueError:
        return str(flag_value)
    # Disable hotkey activation, confirmation prompts, and accessibility shortcut sounds.
    return str(numeric & ~4 & ~8 & ~16)


def refresh_windows_accessibility_settings() -> None:
    try:
        user32.UpdatePerUserSystemParameters = user32.UpdatePerUserSystemParameters
        user32.UpdatePerUserSystemParameters.argtypes = [wintypes.UINT]
        user32.UpdatePerUserSystemParameters.restype = wintypes.BOOL
        user32.UpdatePerUserSystemParameters(1)
    except Exception:
        try:
            subprocess.run(
                ["RUNDLL32.EXE", "USER32.DLL,UpdatePerUserSystemParameters", "1", "True"],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass


def capture_accessibility_state() -> dict:
    import winreg

    snapshot = {}
    for section, config in ACCESSIBILITY_REGISTRY.items():
        snapshot[section] = {}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, config["path"]) as key:
            for value_name in config["values"]:
                value, _ = winreg.QueryValueEx(key, value_name)
                snapshot[section][value_name] = _normalize_registry_value(value)
    return snapshot


def apply_accessibility_state(snapshot: dict) -> None:
    import winreg

    for section, values in snapshot.items():
        config = ACCESSIBILITY_REGISTRY.get(section)
        if not config:
            continue
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, config["path"], 0, winreg.KEY_SET_VALUE) as key:
            for value_name, value in values.items():
                winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, str(value))

    refresh_windows_accessibility_settings()


def build_disabled_accessibility_state(snapshot: dict) -> dict:
    disabled = json.loads(json.dumps(snapshot))
    for section in ("StickyKeys", "KeyboardResponse", "ToggleKeys"):
        if section in disabled and "Flags" in disabled[section]:
            disabled[section]["Flags"] = _disable_accessibility_flag(disabled[section]["Flags"])
    return disabled


def disable_accessibility_hotkeys_with_backup() -> dict:
    current = capture_accessibility_state()
    write_json_file(ACCESSIBILITY_BACKUP_PATH, current)
    apply_accessibility_state(build_disabled_accessibility_state(current))
    return current


def restore_accessibility_hotkeys_from_backup() -> bool:
    backup = read_json_file(ACCESSIBILITY_BACKUP_PATH)
    if not backup:
        return False
    apply_accessibility_state(backup)
    try:
        os.remove(ACCESSIBILITY_BACKUP_PATH)
    except OSError:
        pass
    return True


def get_running_instances() -> list[dict[str, str]]:
    powershell_script = """
$procs = Get-CimInstance Win32_Process -Filter "name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*keyboard_locker.py*" } |
    Select-Object ProcessId, CreationDate, CommandLine

if ($procs) {
    $procs | ConvertTo-Json -Compress
}
"""

    script_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as temp_script:
            temp_script.write(powershell_script)
            script_path = temp_script.name

        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            capture_output=True,
            text=True,
            check=False,
        )
        raw = (result.stdout or "").strip()
        if result.returncode != 0 or not raw:
            return []

        try:
            import json

            parsed = json.loads(raw)
        except Exception:
            return []
    finally:
        if script_path and os.path.exists(script_path):
            try:
                os.remove(script_path)
            except OSError:
                pass

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []

    normalized = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        creation_raw = str(item.get("CreationDate", ""))
        normalized.append(
            {
                "ProcessId": str(item.get("ProcessId", "")),
                "CreationDate": creation_raw,
                "CreationDateIso": convert_creation_date(creation_raw),
                "CommandLine": str(item.get("CommandLine", "")),
            }
        )
    return normalized


def convert_creation_date(raw_value: str) -> str:
    if raw_value.startswith("/Date(") and raw_value.endswith(")/"):
        inner = raw_value[6:-2]
        plus_index = inner.find("+")
        minus_index = inner.find("-")
        cut_indexes = [index for index in (plus_index, minus_index) if index > 0]
        if cut_indexes:
            inner = inner[: min(cut_indexes)]
        try:
            timestamp_ms = int(inner)
            return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone().isoformat()
        except ValueError:
            return raw_value
    return raw_value


def get_autostart_status() -> dict[str, str]:
    run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key) as key:
            value, _ = winreg.QueryValueEx(key, "KeyboardLocker")
            return {"present": "yes", "command": value}
    except OSError:
        return {"present": "no", "command": ""}


class LockerStateMachine:
    def __init__(self, logger, state_writer=None, allow_injected_physical: bool = False, trace_events: bool = False):
        self.log = logger
        self.state_writer = state_writer
        self.allow_injected_physical = allow_injected_physical
        self.trace_events = trace_events
        self.locked = False
        self.exit_requested = False
        self.unlock_scan_buffer = deque(maxlen=len(UNLOCK_SCAN_SEQUENCE))
        self.physical_down: dict[tuple[int, int], KeySnapshot] = {}
        self.seen_locked_events: set[tuple[str, int, int, bool, bool]] = set()

    def _key_id(self, vk_code: int, scan_code: int) -> tuple[int, int]:
        return vk_code, scan_code

    def _update_physical_state(
        self,
        vk_code: int,
        scan_code: int,
        is_keydown: bool,
        is_extended: bool,
        is_injected: bool,
    ) -> None:
        if is_injected and not self.allow_injected_physical:
            return

        key_id = self._key_id(vk_code, scan_code)
        if is_keydown:
            self.physical_down[key_id] = KeySnapshot(vk_code, scan_code, is_extended)
        else:
            self.physical_down.pop(key_id, None)

    def _ctrl_alt_pressed(self) -> bool:
        vk_codes = {snapshot.vk_code for snapshot in self.physical_down.values()}
        return bool(vk_codes & CTRL_VKS) and bool(vk_codes & ALT_VKS)

    def _clear_unlock_buffer(self) -> None:
        self.unlock_scan_buffer.clear()
        self.seen_locked_events.clear()

    def _release_keys_for_lock(self, current_key_id: tuple[int, int]) -> list[KeySnapshot]:
        releases = []
        for key_id, snapshot in self.physical_down.items():
            if key_id != current_key_id:
                releases.append(snapshot)
        return releases

    def _publish_state(self, status: str) -> None:
        if self.state_writer:
            self.state_writer(status=status, locked=self.locked)

    def process_event(
        self,
        vk_code: int,
        scan_code: int,
        is_keydown: bool,
        is_extended: bool,
        is_injected: bool,
    ) -> tuple[bool, list[KeySnapshot], bool]:
        if is_injected and not self.allow_injected_physical and not is_keydown:
            return True, [], False

        self._update_physical_state(vk_code, scan_code, is_keydown, is_extended, is_injected)
        current_key_id = self._key_id(vk_code, scan_code)

        if not self.locked:
            if is_keydown and self._ctrl_alt_pressed() and vk_code == VK_Q:
                self.exit_requested = True
                self.log("Exit hotkey detected while unlocked.")
                return False, [], True

            if is_keydown and self._ctrl_alt_pressed() and scan_code == LOCK_HOTKEY_SCAN_CODE:
                releases = self._release_keys_for_lock(current_key_id)
                self.locked = True
                self._clear_unlock_buffer()
                self._publish_state("running")
                self.log("LOCKED: keyboard input is suppressed. Type physical U N L O C K or press Ctrl+Alt+U.")
                return False, releases, False

            return True, [], False

        if self.trace_events:
            event_key = ("down" if is_keydown else "up", vk_code, scan_code, is_extended, is_injected)
            if event_key not in self.seen_locked_events:
                self.seen_locked_events.add(event_key)
                self.log(
                    f"LOCKED_EVENT type={event_key[0]} vk={vk_code} scan={scan_code} "
                    f"extended={is_extended} injected={is_injected}"
                )

        if is_keydown:
            if self._ctrl_alt_pressed() and vk_code == VK_Q:
                self.exit_requested = True
                self.log("Exit hotkey detected while locked.")
                return False, [], True

            if self._ctrl_alt_pressed() and vk_code == VK_U:
                self.locked = False
                self._clear_unlock_buffer()
                self._publish_state("running")
                self.log("UNLOCKED: keyboard input is active again.")
                return False, [], False

            if scan_code > 0:
                self.unlock_scan_buffer.append(scan_code)

            if tuple(self.unlock_scan_buffer) == UNLOCK_SCAN_SEQUENCE:
                self.locked = False
                self._clear_unlock_buffer()
                self._publish_state("running")
                self.log("UNLOCKED: keyboard input is active again.")
                return False, [], False

        return False, [], False


class KeyboardLocker:
    def __init__(self, allow_injected_physical: bool = False, trace_events: bool = False):
        self.started_at = utc_now_iso()
        self.state = LockerStateMachine(
            log,
            state_writer=self.publish_runtime_state,
            allow_injected_physical=allow_injected_physical,
            trace_events=trace_events,
        )
        self.hook_handle = None
        self.hook_proc = None
        self.mutex_handle = None
        self.registered_hotkey_ids: list[int] = []
        self.accessibility_snapshot = {}

    def acquire_single_instance(self) -> None:
        self.mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        last_error = kernel32.GetLastError()
        if last_error == 183:
            log("Another keyboard locker instance is already running. Exiting.")
            sys.exit(0)

    def release_single_instance(self) -> None:
        if self.mutex_handle:
            kernel32.CloseHandle(self.mutex_handle)
            self.mutex_handle = None

    def _inject_key_up(self, key_snapshot: KeySnapshot) -> None:
        emit_keyboard_event(
            key_snapshot.vk_code,
            key_snapshot.scan_code,
            is_keyup=True,
            extended=key_snapshot.is_extended,
        )

    def request_exit(self) -> None:
        user32.PostQuitMessage(0)

    def publish_runtime_state(self, status: str, locked: bool) -> None:
        payload = build_runtime_state_payload(status=status, locked=locked, pid=get_pid())
        payload["started_at"] = self.started_at
        write_runtime_state(payload)

    def register_locked_top_row_hotkeys(self) -> None:
        if self.registered_hotkey_ids:
            return

        for index, vk_code in enumerate(TOP_ROW_VKS):
            hotkey_id = HOTKEY_ID_BASE + index
            if user32.RegisterHotKey(None, hotkey_id, MOD_NOREPEAT, vk_code):
                self.registered_hotkey_ids.append(hotkey_id)

    def unregister_locked_top_row_hotkeys(self) -> None:
        for hotkey_id in self.registered_hotkey_ids:
            user32.UnregisterHotKey(None, hotkey_id)
        self.registered_hotkey_ids.clear()

    def install_hook(self) -> None:
        def callback(n_code: int, w_param: int, l_param: int) -> int:
            if n_code != HC_ACTION:
                return user32.CallNextHookEx(self.hook_handle, n_code, w_param, l_param)

            data = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            is_keydown = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
            is_keyup = w_param in (WM_KEYUP, WM_SYSKEYUP)
            if not (is_keydown or is_keyup):
                return user32.CallNextHookEx(self.hook_handle, n_code, w_param, l_param)

            is_injected = bool(data.flags & LLKHF_INJECTED)
            is_extended = bool(data.flags & LLKHF_EXTENDED)
            was_locked = self.state.locked
            allow_event, releases, should_exit = self.state.process_event(
                vk_code=int(data.vkCode),
                scan_code=int(data.scanCode),
                is_keydown=is_keydown,
                is_extended=is_extended,
                is_injected=is_injected,
            )

            if self.state.locked != was_locked:
                if self.state.locked:
                    self.register_locked_top_row_hotkeys()
                else:
                    self.unregister_locked_top_row_hotkeys()

            for key_snapshot in releases:
                self._inject_key_up(key_snapshot)

            if should_exit:
                log("Exiting keyboard locker.")
                self.request_exit()

            if allow_event:
                return user32.CallNextHookEx(self.hook_handle, n_code, w_param, l_param)

            return 1

        self.hook_proc = HOOK_PROC(callback)
        self.hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.hook_proc, kernel32.GetModuleHandleW(None), 0)
        if not self.hook_handle:
            raise OSError(f"SetWindowsHookExW failed with error {ctypes.get_last_error()}.")

    def uninstall_hook(self) -> None:
        self.unregister_locked_top_row_hotkeys()
        if self.hook_handle:
            user32.UnhookWindowsHookEx(self.hook_handle)
            self.hook_handle = None
            self.hook_proc = None

    def run(self) -> None:
        self.acquire_single_instance()
        atexit.register(self.release_single_instance)

        self.accessibility_snapshot = disable_accessibility_hotkeys_with_backup()
        self.install_hook()
        self.publish_runtime_state(status="running", locked=False)

        log(f"Keyboard locker is running. version={APP_VERSION} pid={get_pid()}")
        log("Lock: physical Ctrl+Alt+L")
        log("Unlock phrase: physical U N L O C K")
        log("Emergency unlock: Ctrl+Alt+U")
        log("Exit: Ctrl+Alt+Q")
        log(f"Log file: {LOG_PATH}")

        msg = wintypes.MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == 0:
                break
            if result == -1:
                raise OSError("GetMessageW failed.")
            if msg.message == WM_HOTKEY:
                if self.state.trace_events:
                    log(f"LOCKED_HOTKEY id={msg.wParam}")
                continue
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        self.uninstall_hook()
        restore_accessibility_hotkeys_from_backup()
        self.publish_runtime_state(status="stopped", locked=self.state.locked)


def run_self_tests() -> int:
    results = []

    def check(name: str, condition: bool) -> None:
        results.append((name, condition))

    for iteration in range(1, 6):
        locker = LockerStateMachine(lambda message: None)

        allow, releases, should_exit = locker.process_event(ord("L"), 38, True, False, False)
        check(f"{iteration}: plain L does not lock without modifiers", allow and not releases and not should_exit and not locker.locked)

        allow, releases, should_exit = locker.process_event(ord("L"), 38, True, False, True)
        check(f"{iteration}: injected plain L does not lock", allow and not releases and not should_exit and not locker.locked)

        allow, releases, should_exit = locker.process_event(VK_LCONTROL, 29, True, False, False)
        check(f"{iteration}: ctrl down passes before lock", allow and not releases and not should_exit)

        allow, releases, should_exit = locker.process_event(VK_LMENU, 56, True, False, False)
        check(f"{iteration}: alt down passes before lock", allow and not releases and not should_exit)

        allow, releases, should_exit = locker.process_event(ord("L"), 38, True, False, False)
        released_pairs = {(snapshot.vk_code, snapshot.scan_code) for snapshot in releases}
        check(f"{iteration}: lock hotkey suppresses event", not allow and not should_exit)
        check(f"{iteration}: lock transition captures pressed modifiers", released_pairs == {(VK_LCONTROL, 29), (VK_LMENU, 56)})
        check(f"{iteration}: state became locked", locker.locked)

        allow, releases, should_exit = locker.process_event(ord("A"), 30, True, False, False)
        check(f"{iteration}: letters are blocked while locked", not allow and not releases and not should_exit and locker.locked)
        allow, releases, should_exit = locker.process_event(VK_TAB, 15, True, False, False)
        check(f"{iteration}: tab is blocked while locked", not allow and not releases and not should_exit and locker.locked)
        allow, releases, should_exit = locker.process_event(VK_LWIN, 91, True, True, False)
        check(f"{iteration}: windows key is blocked while locked", not allow and not releases and not should_exit and locker.locked)
        allow, releases, should_exit = locker.process_event(VK_VOLUME_UP, 48, True, True, False)
        check(f"{iteration}: media-style vk is blocked while locked", not allow and not releases and not should_exit and locker.locked)

        locker = LockerStateMachine(lambda message: None)
        locker.process_event(VK_LCONTROL, 29, True, False, False)
        locker.process_event(VK_LMENU, 56, True, False, False)
        locker.process_event(ord("L"), 38, True, False, False)
        locker.process_event(ord("L"), 38, False, False, False)
        locker.process_event(VK_LMENU, 56, False, False, False)
        locker.process_event(VK_LCONTROL, 29, False, False, False)
        for scan_code, vk_code in zip(UNLOCK_SCAN_SEQUENCE, map(ord, "UNLOCK")):
            allow, releases, should_exit = locker.process_event(vk_code, scan_code, True, False, False)
        check(f"{iteration}: unlock sequence suppresses final key", not allow and not releases and not should_exit)
        check(f"{iteration}: unlock sequence restores typing state", not locker.locked)

        allow, releases, should_exit = locker.process_event(ord("A"), 30, True, False, False)
        check(f"{iteration}: letters pass after unlock", allow and not releases and not should_exit)

        locker = LockerStateMachine(lambda message: None)
        locker.process_event(VK_LCONTROL, 29, True, False, False)
        locker.process_event(VK_LMENU, 56, True, False, False)
        locker.process_event(ord("L"), 38, True, False, False)
        allow, releases, should_exit = locker.process_event(VK_U, 22, True, False, False)
        check(f"{iteration}: emergency unlock suppresses key", not allow and not releases and not should_exit)
        check(f"{iteration}: emergency unlock restores typing state", not locker.locked)

        locker = LockerStateMachine(lambda message: None)
        locker.process_event(VK_LCONTROL, 29, True, False, False)
        locker.process_event(VK_LMENU, 56, True, False, False)
        allow, releases, should_exit = locker.process_event(VK_Q, 16, True, False, False)
        check(f"{iteration}: exit hotkey is caught while unlocked", not allow and should_exit)

        locker = LockerStateMachine(lambda message: None)
        locker.process_event(VK_LCONTROL, 29, True, False, False)
        locker.process_event(VK_LMENU, 56, True, False, False)
        locker.process_event(ord("L"), 38, True, False, False)
        allow, releases, should_exit = locker.process_event(VK_Q, 16, True, False, False)
        check(f"{iteration}: exit hotkey is caught while locked", not allow and should_exit)

        locker = LockerStateMachine(lambda message: None)
        allow, releases, should_exit = locker.process_event(ord("A"), 30, False, False, True)
        check(f"{iteration}: injected key-up is ignored safely", allow and not releases and not should_exit and not locker.locked)

    failed = [name for name, condition in results if not condition]
    for name, condition in results:
        print(f"{'PASS' if condition else 'FAIL'} {name}")

    if failed:
        print(f"Self-test failed: {len(failed)} checks")
        return 1

    print(f"Self-test passed: {len(results)} checks")
    return 0


def _send_key(vk_code: int, is_keyup: bool = False, extended: bool = False) -> None:
    if vk_code == VK_LCONTROL:
        emit_keyboard_event(vk_code, 29, is_keyup=is_keyup, extended=extended)
        return
    if vk_code == VK_LMENU:
        emit_keyboard_event(vk_code, 56, is_keyup=is_keyup, extended=extended)
        return
    if vk_code == ord("L"):
        emit_keyboard_event(vk_code, 38, is_keyup=is_keyup, extended=extended)
        return
    if vk_code == ord("U"):
        emit_keyboard_event(vk_code, 22, is_keyup=is_keyup, extended=extended)
        return
    if vk_code == ord("N"):
        emit_keyboard_event(vk_code, 49, is_keyup=is_keyup, extended=extended)
        return
    if vk_code == ord("O"):
        emit_keyboard_event(vk_code, 24, is_keyup=is_keyup, extended=extended)
        return
    if vk_code == ord("C"):
        emit_keyboard_event(vk_code, 46, is_keyup=is_keyup, extended=extended)
        return
    if vk_code == ord("K"):
        emit_keyboard_event(vk_code, 37, is_keyup=is_keyup, extended=extended)
        return
    if vk_code == VK_Q:
        emit_keyboard_event(vk_code, 16, is_keyup=is_keyup, extended=extended)
        return

    emit_keyboard_event(vk_code, 0, is_keyup=is_keyup, extended=extended)


def _tap_key(vk_code: int, extended: bool = False, delay: float = 0.03) -> None:
    _send_key(vk_code, is_keyup=False, extended=extended)
    time.sleep(delay)
    _send_key(vk_code, is_keyup=True, extended=extended)
    time.sleep(delay)


def _tap_chord(keys: list[tuple[int, bool]], delay: float = 0.03) -> None:
    for vk_code, extended in keys:
        _send_key(vk_code, is_keyup=False, extended=extended)
        time.sleep(delay)
    for vk_code, extended in reversed(keys):
        _send_key(vk_code, is_keyup=True, extended=extended)
        time.sleep(delay)


def _wait_for_log_text(log_path: str, needle: str, timeout_seconds: float = 5.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as log_file:
                if needle in log_file.read():
                    return True
        time.sleep(0.1)
    return False


def _count_log_text(log_path: str, needle: str) -> int:
    if not os.path.exists(log_path):
        return 0
    with open(log_path, "r", encoding="utf-8") as log_file:
        return log_file.read().count(needle)


def _wait_for_log_count(log_path: str, needle: str, expected_count: int, timeout_seconds: float = 5.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _count_log_text(log_path, needle) >= expected_count:
            return True
        time.sleep(0.1)
    return False


def run_integration_tests() -> int:
    python_exe = sys.executable
    script_path = os.path.abspath(__file__)
    temp_dir = tempfile.mkdtemp(prefix="keyboard-locker-test-")
    log_path = os.path.join(temp_dir, "integration-child.log")
    mutex_name = f"Local\\KeyboardLockerIntegration-{os.getpid()}-{int(time.time())}"
    child = None
    try:
        child = subprocess.Popen(
            [
                python_exe,
                script_path,
                "--allow-injected",
                "--log-path",
                log_path,
                "--mutex-name",
                mutex_name,
            ],
            cwd=os.path.dirname(script_path),
        )

        if not _wait_for_log_text(log_path, "Keyboard locker is running."):
            print("FAIL integration child did not start")
            return 1

        results = []

        def check(name: str, condition: bool) -> None:
            results.append((name, condition))
            print(f"{'PASS' if condition else 'FAIL'} {name}")

        for iteration in range(1, 6):
            locked_before = _count_log_text(log_path, "LOCKED:")
            unlocked_before = _count_log_text(log_path, "UNLOCKED:")

            _tap_chord([(VK_LCONTROL, False), (VK_LMENU, False), (ord("L"), False)])
            check(f"{iteration}: lock event logged", _wait_for_log_count(log_path, "LOCKED:", locked_before + 1, 2.0))

            _tap_key(ord("B"))
            time.sleep(0.1)
            check(f"{iteration}: lock state is still stable after blocked key", _count_log_text(log_path, "LOCKED:") == locked_before + 1)

            for vk_code in map(ord, "UNLOCK"):
                _tap_key(vk_code)
            check(f"{iteration}: unlock event logged", _wait_for_log_count(log_path, "UNLOCKED:", unlocked_before + 1, 2.0))

            _tap_chord([(VK_LCONTROL, False), (VK_LMENU, False), (ord("L"), False)])
            _wait_for_log_count(log_path, "LOCKED:", locked_before + 2, 2.0)
            _tap_chord([(VK_LCONTROL, False), (VK_LMENU, False), (VK_U, False)])
            check(f"{iteration}: emergency unlock event logged", _wait_for_log_count(log_path, "UNLOCKED:", unlocked_before + 2, 2.0))

        failed = [name for name, condition in results if not condition]
        if failed:
            print(f"Integration test failed: {len(failed)} checks")
            return 1

        _tap_chord([(VK_LCONTROL, False), (VK_LMENU, False), (ord("L"), False)])
        time.sleep(0.2)
        _tap_chord([(VK_LCONTROL, False), (VK_LMENU, False), (VK_Q, False)])
        time.sleep(0.3)
        check("exit hotkey while locked event logged", _wait_for_log_text(log_path, "Exit hotkey detected while locked.", 2.0))
        check("exit event logged", _wait_for_log_text(log_path, "Exiting keyboard locker.", 2.0))

        print(f"Integration test passed: {len(results)} checks")
        return 0
    finally:
        if child and child.poll() is None:
            try:
                _tap_chord([(VK_LCONTROL, False), (VK_LMENU, False), (VK_Q, False)])
                time.sleep(0.2)
            except Exception:
                pass
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except Exception:
                    child.kill()


def run_status() -> int:
    print(f"version={APP_VERSION}")
    print(f"log_path={LOG_PATH}")
    print(f"state_path={STATE_PATH}")
    print(f"mutex_name={MUTEX_NAME}")
    print(f"status_pid={get_pid()}")
    print("mode=status")

    autostart = get_autostart_status()
    print(f"autostart={'present' if autostart['present'] == 'yes' else 'missing'}")
    if autostart["command"]:
        print(f"autostart_command={autostart['command']}")

    if os.path.exists(LOG_PATH):
        print(f"log_exists=yes")
        print(f"log_size={os.path.getsize(LOG_PATH)}")
    else:
        print("log_exists=no")

    instances = get_running_instances()
    print(f"running_instances={len(instances)}")
    for index, instance in enumerate(instances, start=1):
        print(f"running_{index}_pid={instance['ProcessId']}")
        print(f"running_{index}_created={instance['CreationDateIso']}")
        print(f"running_{index}_created_raw={instance['CreationDate']}")
        print(f"running_{index}_command={instance['CommandLine']}")

    runtime_state = read_runtime_state()
    runtime_stale = False
    if runtime_state:
        runtime_stale = runtime_state.get("status") == "running" and (
            len(instances) != 1 or str(runtime_state.get("pid", "")) != str(instances[0]["ProcessId"])
        )
        print("runtime_state=present")
        for key in ("status", "locked", "pid", "started_at", "updated_at", "version"):
            if key in runtime_state:
                print(f"runtime_{key}={runtime_state[key]}")
        print(f"runtime_stale={'yes' if runtime_stale else 'no'}")
    else:
        print("runtime_state=missing")

    return 0


def run_healthcheck() -> int:
    instances = get_running_instances()
    autostart = get_autostart_status()
    runtime_state = read_runtime_state()
    runtime_matches = (
        bool(runtime_state)
        and runtime_state.get("status") == "running"
        and len(instances) == 1
        and str(runtime_state.get("pid", "")) == str(instances[0]["ProcessId"])
    )
    runtime_stale = bool(runtime_state) and runtime_state.get("status") == "running" and not runtime_matches
    healthy = len(instances) == 1 and autostart["present"] == "yes" and runtime_matches

    print(f"version={APP_VERSION}")
    print(f"healthy={'yes' if healthy else 'no'}")
    print(f"running_instances={len(instances)}")
    print(f"autostart_present={autostart['present']}")
    print(f"runtime_state_present={'yes' if runtime_state else 'no'}")
    print(f"runtime_matches_process={'yes' if runtime_matches else 'no'}")
    print(f"runtime_stale={'yes' if runtime_stale else 'no'}")
    print(f"runtime_failed={'yes' if runtime_state.get('status') == 'failed' else 'no'}")
    if instances:
        print(f"primary_pid={instances[0]['ProcessId']}")
        print(f"primary_created={instances[0]['CreationDateIso']}")
    if runtime_state:
        print(f"runtime_status={runtime_state.get('status')}")
        print(f"runtime_locked={runtime_state.get('locked')}")
        print(f"runtime_pid={runtime_state.get('pid')}")
        print(f"runtime_updated_at={runtime_state.get('updated_at')}")

    return 0 if healthy else 1


def run_write_state_stopped() -> int:
    payload = build_runtime_state_payload(status="stopped", locked=False, pid=0)
    write_runtime_state(payload)
    print(f"state_written={STATE_PATH}")
    print("state_status=stopped")
    return 0


def run_write_state_failed() -> int:
    payload = build_runtime_state_payload(status="failed", locked=False, pid=get_pid())
    write_runtime_state(payload)
    print(f"state_written={STATE_PATH}")
    print("state_status=failed")
    return 0


def run_disable_accessibility_hotkeys() -> int:
    disable_accessibility_hotkeys_with_backup()
    print(f"accessibility_backup_written={ACCESSIBILITY_BACKUP_PATH}")
    print("accessibility_hotkeys=disabled")
    return 0


def run_restore_accessibility_hotkeys() -> int:
    restored = restore_accessibility_hotkeys_from_backup()
    print(f"accessibility_hotkeys_restored={'yes' if restored else 'no'}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--integration-test", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--write-state-stopped", action="store_true")
    parser.add_argument("--write-state-failed", action="store_true")
    parser.add_argument("--disable-accessibility-hotkeys", action="store_true")
    parser.add_argument("--restore-accessibility-hotkeys", action="store_true")
    parser.add_argument("--clear-log", action="store_true")
    parser.add_argument("--allow-injected", action="store_true")
    parser.add_argument("--trace-events", action="store_true")
    parser.add_argument("--log-path", default=DEFAULT_LOG_PATH)
    parser.add_argument("--state-path", default=DEFAULT_STATE_PATH)
    parser.add_argument("--accessibility-backup-path", default=DEFAULT_ACCESSIBILITY_BACKUP_PATH)
    parser.add_argument("--mutex-name", default=DEFAULT_MUTEX_NAME)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    global LOG_PATH
    global STATE_PATH
    global ACCESSIBILITY_BACKUP_PATH
    global MUTEX_NAME

    LOG_PATH = os.path.abspath(args.log_path)
    STATE_PATH = os.path.abspath(args.state_path)
    ACCESSIBILITY_BACKUP_PATH = os.path.abspath(args.accessibility_backup_path)
    MUTEX_NAME = args.mutex_name

    if args.clear_log and os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)

    if args.self_test:
        return run_self_tests()
    if args.integration_test:
        return run_integration_tests()
    if args.status:
        return run_status()
    if args.healthcheck:
        return run_healthcheck()
    if args.write_state_stopped:
        return run_write_state_stopped()
    if args.write_state_failed:
        return run_write_state_failed()
    if args.disable_accessibility_hotkeys:
        return run_disable_accessibility_hotkeys()
    if args.restore_accessibility_hotkeys:
        return run_restore_accessibility_hotkeys()

    locker = KeyboardLocker(
        allow_injected_physical=args.allow_injected,
        trace_events=args.trace_events,
    )
    locker.run()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        try:
            write_runtime_state(build_runtime_state_payload(status="failed", locked=False, pid=get_pid()))
        except Exception:
            pass
        log("Unhandled exception:")
        log(traceback.format_exc())
        raise
