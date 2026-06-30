#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Pango

import json
import os
import subprocess
import time
import shutil
import sqlite3
from pathlib import Path
from copy import deepcopy
import re

HOME = Path.home()
CONFIG_PATH          = HOME / ".config/quickshell/data/config.json"
APPS_PATH            = HOME / ".config/quickshell/data/apps.json"
KEYBINDS_SYSTEM_PATH = HOME / ".config/hypr/configs/Keybinds.conf"
KEYBINDS_USER_PATH   = HOME / ".config/hypr/UserConfigs/UserKeybinds.conf"
KEYBINDS_LAUNCHER_PATH = HOME / ".config/hypr/UserConfigs/UserLauncherBinds.conf"
USER_DEFAULTS_PATH   = HOME / ".config/hypr/UserConfigs/01-UserDefaults.conf"
ENV_VARIABLES_PATH   = HOME / ".config/hypr/UserConfigs/ENVariables.conf"
STARTUP_APPS_PATH    = HOME / ".config/hypr/UserConfigs/Startup_Apps.conf"
WINDOW_RULES_PATH    = HOME / ".config/hypr/UserConfigs/WindowRules.conf"
POWER_SCRIPT         = HOME / ".config/hypr/scripts/PowerProfileAuto.sh"
HYPRIDLE_CONF_PATH   = HOME / ".config/hypr/hypridle.conf"
WAYBAR_LAYOUTS_DIR   = HOME / ".config/waybar/configs"
WAYBAR_STYLES_DIR    = HOME / ".config/waybar/style"
WAYBAR_CONFIG_LINK   = HOME / ".config/waybar/config"
WAYBAR_STYLE_LINK    = HOME / ".config/waybar/style.css"
WAYBAR_STARTUP_LOG   = HOME / ".cache/quickshell/waybar-startup.log"
SKWD_WALL_CONFIG_PATH = HOME / ".config/skwd-wall/config.json"
POSITIONS_JSON_PATH  = HOME / ".config/quickshell/components/ModernClockWidget/positions.json"
SKWD_WALL_CACHE_DIR  = Path(os.environ.get("SKWD_WALL_CACHE", HOME / ".cache/skwd-wall"))
WORKSPACES_CONF_PATH = HOME / ".config/hypr/workspaces.conf"

KNOWN_TERMINALS = [
    "kitty",
    "alacritty",
    "foot",
    "wezterm",
    "konsole",
    "gnome-terminal",
    "xfce4-terminal",
    "lxterminal",
    "terminology",
    "terminator",
    "xterm",
    "uxterm",
    "rxvt",
    "urxvt",
    "eterm",
    "tilix",
    "cool-retro-term",
    "st",
    "blackbox",
    "kgx", # GNOME Console
    "hyper",
]

KNOWN_SHELLS = [
    "zsh",
    "bash",
    "fish",
    "sh",
    "dash",
    "mksh",
]

GPU_PRESET_ENV = {
    "auto": [],
    "nvidia": [
        "env = LIBVA_DRIVER_NAME,nvidia",
        "env = __GLX_VENDOR_LIBRARY_NAME,nvidia",
        "env = NVD_BACKEND,direct",
    ],
    "amd": [
        "env = LIBVA_DRIVER_NAME,amdgpu",
        "env = VDPAU_DRIVER,va_gl",
    ],
    "intel": [
        "env = LIBVA_DRIVER_NAME,iHD",
        "env = VDPAU_DRIVER,va_gl",
    ],
    "other": [
        "env = LIBVA_DRIVER_NAME,",
        "env = VDPAU_DRIVER,",
    ],
}

THEME_MODE_PATH = HOME / ".cache/.theme_mode"

_LAST_WAYBAR_LOG_POS = 0
_LAST_WAYBAR_STYLE = ""


# ── Config I/O ────────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2) + "\n")

def get_nested(data, keys, fallback=None):
    o = data
    for k in keys:
        if not isinstance(o, dict):
            return fallback
        o = o.get(k)
        if o is None:
            return fallback
    return o if o is not None else fallback

def set_nested(data, keys, value):
    o = data
    for k in keys[:-1]:
        if k not in o or not isinstance(o[k], dict):
            o[k] = {}
        o = o[k]
    o[keys[-1]] = value


# ── Keybind helpers ───────────────────────────────────────────────────────────

def _auto_description(dispatcher: str, arg: str) -> str:
    d = (dispatcher or "").lower().strip()
    a = (arg or "").strip()
    if d == "exec":
        if "kitty" in a or "$term" in a: return "Open terminal"
        if "firefox" in a: return "Open Firefox"
        if "screenshot" in a or "ScreenShot" in a: return "Screenshot"
        if "windowswitcher" in a: return "Window switcher"
        if "applauncher" in a: return "App launcher"
        if "config toggle" in a: return "Config panel"
        return "Run command"
    if d == "killactive": return "Close window"
    if d == "workspace": return "Switch workspace"
    if d == "movefocus": return "Move focus"
    if d == "fullscreen": return "Toggle fullscreen"
    if d == "togglefloating": return "Toggle floating"
    return dispatcher or "Custom bind"

def _split_spec(spec: str) -> list[str]:
    out, current = [], ""
    for ch in spec:
        if ch == "," and len(out) < 3:
            out.append(current.strip())
            current = ""
        else:
            current += ch
    out.append(current.strip())
    return out

def _is_bind_line(line: str) -> bool:
    return bool(re.match(r'^(#\s*)?(bind[a-z]*)\s*=\s*', line.strip(), re.I))

def _parse_keybinds(text: str, source_tag: str) -> list[dict]:
    binds = []
    for i, original in enumerate(text.splitlines()):
        trimmed = original.strip()
        if not trimmed:
            continue
        commented = trimmed.startswith("#")
        parse = re.sub(r'^#\s*', '', trimmed) if commented else trimmed
        m = re.match(r'^(bind[a-z]*)\s*=\s*(.+)$', parse, re.I)
        if not m:
            continue
        bind_type, spec = m.group(1), m.group(2)
        description = ""
        if "#" in spec:
            idx = spec.index("#")
            description = spec[idx+1:].strip()
            spec = spec[:idx].strip()
        parts = _split_spec(spec)
        if len(parts) < 3:
            continue
        mods, key, dispatcher = parts[0], parts[1], parts[2]
        arg = ", ".join(parts[3:]) if len(parts) > 3 else ""
        binds.append({
            "uid": f"{source_tag}:{i}",
            "source": source_tag,
            "line_index": i,
            "enabled": not commented,
            "type": bind_type,
            "mods": mods.strip(),
            "key": key.strip(),
            "dispatcher": dispatcher.strip(),
            "arg": arg.strip(),
            "description": description or _auto_description(dispatcher, arg),
        })
    return binds

def _compose_bind_line(bind: dict) -> str:
    line = f"{bind['type']} = {bind['mods']}, {bind['key']}, {bind['dispatcher']}"
    if bind["arg"]:
        line += f", {bind['arg']}"
    if bind["description"]:
        line += f" # {bind['description']}"
    return ("# " if not bind["enabled"] else "") + line

def rebuild_keybind_file(original_lines: list[str], binds: list[dict]) -> str:
    keep = [l for l in original_lines if not _is_bind_line(l)]
    while keep and not keep[-1].strip():
        keep.pop()
    bind_lines = [_compose_bind_line(b) for b in binds]
    if bind_lines and keep:
        keep.append("")
    return "\n".join(keep + bind_lines) + "\n"


# ── Apply side effects ────────────────────────────────────────────────────────

def _run(cmd, shell=False):
    try:
        subprocess.Popen(cmd, shell=shell, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _run_wait(cmd, shell=False):
    try:
        subprocess.run(cmd, shell=shell, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _is_waybar_running() -> bool:
    try:
        return subprocess.run(
            ["pgrep", "-x", "waybar"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
    except Exception:
        return False

def _start_waybar_checked(
    cfg_path: str,
    style_path: str,
    timeout_sec: float = 5.0,
    stable_sec: float = 1.8,
) -> bool:
    global _LAST_WAYBAR_LOG_POS, _LAST_WAYBAR_STYLE
    try:
        WAYBAR_STARTUP_LOG.parent.mkdir(parents=True, exist_ok=True)
        try:
            _LAST_WAYBAR_LOG_POS = WAYBAR_STARTUP_LOG.stat().st_size
        except Exception:
            _LAST_WAYBAR_LOG_POS = 0
        _LAST_WAYBAR_STYLE = style_path
        with WAYBAR_STARTUP_LOG.open("a", encoding="utf-8") as logf:
            proc = subprocess.Popen(
                ["waybar", "-c", cfg_path, "-s", style_path],
                stdout=logf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except Exception:
        return False

    start_ts = time.time()
    first_seen_ts = None
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        running = _is_waybar_running()

        # Some environments can make the parent process exit while Waybar keeps
        # running in a child/session. Only fail when BOTH are not alive.
        if proc.poll() is not None and not running:
            return False

        if running and first_seen_ts is None:
            first_seen_ts = time.time()

        # Require the process to remain alive for a short grace period.
        if running and first_seen_ts is not None and (time.time() - first_seen_ts) >= stable_sec:
            return True

        # Hard guard: if process never appeared quickly enough, fail fast.
        if first_seen_ts is None and (time.time() - start_ts) > timeout_sec:
            return False

        time.sleep(0.1)
    return _is_waybar_running() and proc.poll() is None

def _waybar_last_error_summary(max_lines: int = 160, style_path: str = "") -> str:
    try:
        if not WAYBAR_STARTUP_LOG.exists():
            return ""

        start_pos = _LAST_WAYBAR_LOG_POS if _LAST_WAYBAR_LOG_POS >= 0 else 0
        with WAYBAR_STARTUP_LOG.open("rb") as fh:
            fh.seek(start_pos)
            chunk = fh.read()
        text = chunk.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        tail = lines[-max_lines:] if len(lines) > max_lines else lines

        style_hint = Path(style_path or _LAST_WAYBAR_STYLE).name.strip().lower()

        if style_hint:
            for line in reversed(tail):
                line_s = line.strip()
                if "[error]" in line_s and style_hint in line_s.lower():
                    msg = line_s.split("[error]", 1)[-1].strip()
                    return msg[:180]

        for line in reversed(tail):
            line_s = line.strip()
            if "[error]" in line_s:
                # Keep the part after [error] when present.
                msg = line_s.split("[error]", 1)[-1].strip()
                return msg[:180]
        return ""
    except Exception:
        return ""

def apply_waybar(enabled: bool, cfg_path: str, style_path: str, restart: bool = False):
    if enabled:
        if restart:
            # Stop must be synchronous; async pkill can kill the new process.
            _run_wait("pkill -x waybar || true", shell=True)
            return _start_waybar_checked(cfg_path, style_path)
        else:
            if _is_waybar_running():
                return True
            return _start_waybar_checked(cfg_path, style_path)
    else:
        _run_wait("pkill -x waybar || true", shell=True)
        return True

def sync_waybar_links(cfg_path: str, style_path: str):
    _run(f"ln -sf {json.dumps(cfg_path)} {json.dumps(str(WAYBAR_CONFIG_LINK))}", shell=True)
    _run(f"ln -sf {json.dumps(style_path)} {json.dumps(str(WAYBAR_STYLE_LINK))}", shell=True)

def apply_power_profile():
    if POWER_SCRIPT.exists():
        _run([str(POWER_SCRIPT)])

def _visual_toggles_from_config(config: dict) -> dict:
    return {
        "disableBorders": bool(get_nested(config, ["optimization", "toggles", "disableBorders"], False)),
        "disableTransparency": bool(get_nested(config, ["optimization", "toggles", "disableTransparency"], False)),
        "disableAnimations": bool(get_nested(config, ["optimization", "toggles", "disableAnimations"], False)),
        "disableBlur": bool(get_nested(config, ["optimization", "toggles", "disableBlur"], False)),
        "disableShadows": bool(get_nested(config, ["optimization", "toggles", "disableShadows"], False)),
        "disableRounding": bool(get_nested(config, ["optimization", "toggles", "disableRounding"], False)),
        "disableGaps": bool(get_nested(config, ["optimization", "toggles", "disableGaps"], False)),
        "disableDimInactive": bool(get_nested(config, ["optimization", "toggles", "disableDimInactive"], False)),
    }


def apply_visual_toggles(config: dict):
    toggles = _visual_toggles_from_config(config)

    animations_enabled = 0 if toggles["disableAnimations"] else 1
    blur_enabled = 0 if toggles["disableBlur"] else 1
    shadow_enabled = 0 if toggles["disableShadows"] else 1
    dim_inactive = 0 if toggles["disableDimInactive"] else 1
    inactive_opacity = 1.0 if toggles["disableTransparency"] else 0.9
    gaps_in = 0 if toggles["disableGaps"] else 2
    gaps_out = 0 if toggles["disableGaps"] else 4
    border_size = 0 if toggles["disableBorders"] else 2
    rounding = 0 if toggles["disableRounding"] else 10

    batch = (
        f"keyword animations:enabled {animations_enabled};"
        f"keyword decoration:blur:enabled {blur_enabled};"
        f"keyword decoration:shadow:enabled {shadow_enabled};"
        f"keyword decoration:dim_inactive {dim_inactive};"
        "keyword decoration:active_opacity 1.0;"
        f"keyword decoration:inactive_opacity {inactive_opacity};"
        f"keyword general:gaps_in {gaps_in};"
        f"keyword general:gaps_out {gaps_out};"
        f"keyword general:border_size {border_size};"
        f"keyword decoration:rounding {rounding}"
    )
    _run(["hyprctl", "--batch", batch])


def _snapshot_component_state(config: dict) -> dict:
    return {
        "barEnabled": bool(get_nested(config, ["components", "bar", "enabled"], True)),
        "appLauncher": bool(get_nested(config, ["components", "appLauncher"], True)),
        "windowSwitcher": bool(get_nested(config, ["components", "windowSwitcher"], True)),
        "notifications": bool(get_nested(config, ["components", "notifications"], True)),
        "lockscreen": bool(get_nested(config, ["components", "lockscreen"], False)),
        "smartHome": bool(get_nested(config, ["components", "smartHome"], False)),
        "powerMenu": bool(get_nested(config, ["components", "powerMenu", "enabled"], True)),
        "wallpaperSelector": bool(get_nested(config, ["components", "wallpaperSelector", "enabled"], True)),
    }


def _apply_optimization_component_mode(config: dict, enabled: bool) -> bool:
    changed = False
    saved_state = get_nested(config, ["optimization", "restoreState"], None)

    if enabled:
        if not isinstance(saved_state, dict):
            set_nested(config, ["optimization", "restoreState"], _snapshot_component_state(config))
            changed = True

        desired = {
            ("components", "bar", "enabled"): False,
            ("components", "appLauncher"): False,
            ("components", "windowSwitcher"): False,
            ("components", "notifications"): False,
            ("components", "lockscreen"): False,
            ("components", "smartHome"): False,
            ("components", "powerMenu", "enabled"): False,
            ("components", "wallpaperSelector", "enabled"): True,
        }
        for key_path, value in desired.items():
            current = get_nested(config, list(key_path), None)
            if current != value:
                set_nested(config, list(key_path), value)
                changed = True
        return changed

    if isinstance(saved_state, dict):
        restore_map = {
            ("components", "bar", "enabled"): bool(saved_state.get("barEnabled", True)),
            ("components", "appLauncher"): bool(saved_state.get("appLauncher", True)),
            ("components", "windowSwitcher"): bool(saved_state.get("windowSwitcher", True)),
            ("components", "notifications"): bool(saved_state.get("notifications", True)),
            ("components", "lockscreen"): bool(saved_state.get("lockscreen", False)),
            ("components", "smartHome"): bool(saved_state.get("smartHome", False)),
            ("components", "powerMenu", "enabled"): bool(saved_state.get("powerMenu", True)),
            ("components", "wallpaperSelector", "enabled"): bool(saved_state.get("wallpaperSelector", True)),
        }
        for key_path, value in restore_map.items():
            current = get_nested(config, list(key_path), None)
            if current != value:
                set_nested(config, list(key_path), value)
                changed = True
        set_nested(config, ["optimization", "restoreState"], None)
        changed = True

    return changed


def apply_hypr_reload():
    _run(["hyprctl", "reload"])
    # Wait longer to avoid race condition where hyprctl reload overwrites the toggles
    _run(["bash", "-lc", "sleep 1.5 && $HOME/.config/hypr/scripts/ApplyOptimizationState.sh >/dev/null 2>&1 &"])

def _replace_timeout_in_listener_block(block: str, seconds: int) -> str:
    return re.sub(
        r'(?m)^(\s*timeout\s*=\s*)\d+(\s*(?:#.*)?)$',
        rf'\g<1>{int(seconds)}\2',
        block,
        count=1,
    )

def sync_hypridle_conf(warn_seconds: int, lock_seconds: int, ignore_dbus_inhibit: bool) -> bool:
    if not HYPRIDLE_CONF_PATH.exists():
        return False

    text = HYPRIDLE_CONF_PATH.read_text()
    changed = False

    listener_re = re.compile(r'(?ms)^\s*listener\s*\{.*?^\s*\}')
    state = {"warn": False, "lock": False}

    def repl(match):
        nonlocal changed
        block = match.group(0)
        lowered = block.lower()

        if ("on-timeout" in lowered and "notify-send" in lowered and not state["warn"]):
            state["warn"] = True
            new_block = _replace_timeout_in_listener_block(block, warn_seconds)
            if new_block != block:
                changed = True
            return new_block

        if ("on-timeout" in lowered and "loginctl lock-session" in lowered and not state["lock"]):
            state["lock"] = True
            new_block = _replace_timeout_in_listener_block(block, lock_seconds)
            if new_block != block:
                changed = True
            return new_block

        return block

    text_after_listeners = listener_re.sub(repl, text)

    ignore_re = re.compile(r'(?m)^(\s*ignore_dbus_inhibit\s*=\s*)(true|false)(\s*(?:#.*)?)$')
    ignore_value = "true" if ignore_dbus_inhibit else "false"
    text_after_ignore, ignore_count = ignore_re.subn(rf'\1{ignore_value}\3', text_after_listeners, count=1)
    if ignore_count > 0 and text_after_ignore != text_after_listeners:
        changed = True

    if changed:
        HYPRIDLE_CONF_PATH.write_text(text_after_ignore)

    return changed

def apply_hypridle_enabled(enabled: bool):
    _run_wait("pkill -x hypridle || true", shell=True)
    if enabled:
        _run(["hypridle"])

def _read_text(path: Path) -> str:
    try:
        return path.read_text()
    except Exception:
        return ""

def _write_text(path: Path, text: str):
    path.write_text(text if text.endswith("\n") else text + "\n")

def _detect_terminals() -> list[str]:
    detected = []
    for terminal in KNOWN_TERMINALS:
        if shutil.which(terminal):
            detected.append(terminal)
    if "kitty" not in detected:
        detected.insert(0, "kitty")
    return detected

def _detect_shells() -> list[str]:
    detected = []
    for shell in KNOWN_SHELLS:
        if shutil.which(shell):
            detected.append(shell)
    if "zsh" not in detected:
        detected.insert(0, "zsh")
    return detected

def _detect_monitors() -> list[str]:
    try:
        result = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True)
        if result.returncode == 0:
            monitors = json.loads(result.stdout)
            names = [m["name"] for m in monitors if "name" in m]
            if names:
                return names
    except Exception:
        pass
    return ["auto"]

def _get_monitor_var(index: int) -> str:
    vars = ["main_monitor", "secondary_monitor", "tertiary_monitor"]
    if index < len(vars):
        return vars[index]
    return f"monitor_{index + 1}"

def _sync_userdefaults_monitors(monitors: list[str]) -> bool:
    text = _read_text(USER_DEFAULTS_PATH)
    if not text:
        return False
    
    # Ensure header exists
    header = "# --- Monitores ---"
    if header not in text:
        text = f"{header}\n\n" + text
        
    lines = text.splitlines()
    header_idx = -1
    for i, line in enumerate(lines):
        if header in line:
            header_idx = i
            break
            
    # Find block of monitor variables
    start_vars = header_idx + 1
    while start_vars < len(lines) and not lines[start_vars].strip():
        start_vars += 1
        
    end_vars = start_vars
    while end_vars < len(lines) and lines[end_vars].startswith("$") and "monitor" in lines[end_vars]:
        end_vars += 1
        
    # Rebuild the variable list
    new_vars = [f"${_get_monitor_var(i)} = {m}" for i, m in enumerate(monitors)]
    
    lines[start_vars:end_vars] = new_vars
    new_text = "\n".join(lines)
    
    if new_text.strip() != text.strip():
        _write_text(USER_DEFAULTS_PATH, new_text)
        return True
    return False

def _sync_userdefaults_terminal(terminal: str) -> bool:
    text = _read_text(USER_DEFAULTS_PATH)
    if not text:
        return False
    current = _read_userdefaults_terminal()
    if current == terminal:
        return False
    new_text, count = re.subn(r'(?m)^(\$term\s*=\s*).*$' , rf'\1{terminal}', text, count=1)
    if count:
        _write_text(USER_DEFAULTS_PATH, new_text)
        return True
    return False

def _sync_userdefaults_shell(shell: str) -> bool:
    text = _read_text(USER_DEFAULTS_PATH)
    if not text:
        return False
    current = _read_userdefaults_shell()
    if current == shell:
        return False
    
    # Check if $shell variable exists in the file
    if re.search(r'(?m)^\$shell\s*=\s*', text):
        new_text, count = re.subn(r'(?m)^(\$shell\s*=\s*).*$' , rf'\1{shell}', text, count=1)
    else:
        # Append it before $term or at the end
        new_text = text.replace("$term =", f"$shell = {shell}\n$term =", 1)
        if new_text == text: # fallback
             new_text = text + f"\n$shell = {shell}\n"
        count = 1

    if count:
        _write_text(USER_DEFAULTS_PATH, new_text)
        return True
    return False

def _get_monitor_label(index: int) -> str:
    labels = ["Primary", "Secondary", "Tertiary"]
    if index < len(labels):
        return f"{labels[index]} Monitor"
    return f"Monitor {index + 1}"

def _sync_waybar_monitors(monitors: list[str], secondary_enabled: bool = True):
    cfg_data = load_json(CONFIG_PATH)
    raw = str(get_nested(cfg_data, ["components", "bar", "waybarConfig"], "~/.config/waybar/config"))
    config_path = Path(raw.replace("~", str(HOME)))
    if WAYBAR_CONFIG_LINK.exists():
        try:
            config_path = WAYBAR_CONFIG_LINK.resolve()
        except:
            pass

    if not config_path.exists():
        return

    # Build effective per-bar output list:
    # Bar 0 → primary; Bar 1 → secondary if enabled and available, else "none"
    effective: list[str] = []
    if monitors:
        effective.append(monitors[0])
    secondary = monitors[1] if len(monitors) > 1 and monitors[1] not in ("auto", "", None) else None
    effective.append(secondary if (secondary and secondary_enabled) else "none")

    try:
        content = config_path.read_text()
        output_pattern = r'"output":\s*"[^"]+"'

        for i, m in enumerate(effective):
            label = _get_monitor_label(i)
            comment_pattern = rf'//.*?{label}.*?'
            if re.search(comment_pattern, content, re.IGNORECASE):
                content = re.sub(
                    rf'({comment_pattern})\n(\s*"output":\s*")[^"]+"',
                    rf'\1\n\2{m}"',
                    content,
                    flags=re.IGNORECASE
                )
            else:
                matches = list(re.finditer(output_pattern, content))
                if len(matches) > i:
                    start, end = matches[i].span()
                    content = content[:start] + f'"output": "{m}"' + content[end:]

        config_path.write_text(content)
    except Exception as e:
        print(f"ConfigPanel: failed to sync Waybar monitors: {e}")

def _sync_workspaces_conf(monitors: list[str]) -> bool:
    primary = monitors[0] if monitors else "auto"
    secondary = monitors[1] if len(monitors) > 1 and monitors[1] not in ("auto", "", None) else None

    lines = [
        "# /* ---- 💫 https://github.com/JaKooLit 💫 ---- */  #",
        "# Contributor: sadrach34 (mods and maintenance)",
        "",
        "# Workspaces auto-generated by SDRX Settings — 5 per monitor.",
        "# https://wiki.hyprland.org/Configuring/Workspace-Rules/",
        "",
        f"# Primary ({primary})",
    ]
    for ws in range(1, 6):
        suffix = ", default:true" if ws == 1 else ""
        lines.append(f"workspace = {ws}, monitor:{primary}{suffix}")

    if secondary:
        lines.append(f"\n# Secondary ({secondary})")
        for ws in range(6, 11):
            suffix = ", default:true" if ws == 6 else ""
            lines.append(f"workspace = {ws}, monitor:{secondary}{suffix}")
    else:
        lines.append("")
        for ws in range(6, 11):
            lines.append(f"workspace = {ws}, monitor:{primary}")

    content = "\n".join(lines) + "\n"
    try:
        current = WORKSPACES_CONF_PATH.read_text() if WORKSPACES_CONF_PATH.exists() else ""
        if current == content:
            return False
        WORKSPACES_CONF_PATH.write_text(content)
        return True
    except Exception as e:
        print(f"ConfigPanel: failed to write workspaces.conf: {e}")
        return False

def _read_userdefaults_terminal() -> str:
    text = _read_text(USER_DEFAULTS_PATH)
    match = re.search(r'(?m)^\$term\s*=\s*(.+?)\s*$', text)
    return match.group(1).strip() if match else "kitty"

def _read_userdefaults_shell() -> str:
    text = _read_text(USER_DEFAULTS_PATH)
    match = re.search(r'(?m)^\$shell\s*=\s*(.+?)\s*$', text)
    return match.group(1).strip() if match else "zsh"

def _read_compositor() -> str:
    value = get_nested(load_json(CONFIG_PATH), ["compositor"], "hyprland")
    return str(value or "hyprland")

def _read_theme_mode() -> str:
    try:
        value = THEME_MODE_PATH.read_text().strip().lower()
        return value if value in {"dark", "light"} else "dark"
    except Exception:
        return "dark"

def _sync_theme_mode(mode: str) -> bool:
    mode = (mode or "dark").strip().lower()
    if mode not in {"dark", "light"}:
        mode = "dark"
    current = _read_theme_mode()
    THEME_MODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if current == mode:
        THEME_MODE_PATH.write_text(mode + "\n")
        return False
    opposite = "light" if mode == "dark" else "dark"
    THEME_MODE_PATH.write_text(opposite + "\n")
    script = HOME / ".config/hypr/scripts/DarkLight.sh"
    if script.exists():
        _run([str(script)])
        return True
    THEME_MODE_PATH.write_text(mode + "\n")
    return False

def _read_gpu_vendor() -> str:
    text = _read_text(ENV_VARIABLES_PATH).lower()
    if "nvidia" in text:
        return "nvidia"
    if "amdgpu" in text or "amd" in text:
        return "amd"
    if "iHD".lower() in text or "intel" in text:
        return "intel"
    return "auto"

def _sync_envariables_gpu(vendor: str) -> bool:
    text = _read_text(ENV_VARIABLES_PATH)
    if not text:
        return False
    if _read_gpu_vendor() == vendor:
        return False

    lines = text.splitlines()
    preserved = []
    for line in lines:
        if any(key in line for key in ["LIBVA_DRIVER_NAME", "__GLX_VENDOR_LIBRARY_NAME", "NVD_BACKEND", "VDPAU_DRIVER", "GBM_BACKEND", "WLR_RENDERER_ALLOW_SOFTWARE"]):
            continue
        preserved.append(line)

    additions = GPU_PRESET_ENV.get(vendor, GPU_PRESET_ENV["auto"])
    if additions:
        preserved.append("")
        preserved.extend(additions)

    _write_text(ENV_VARIABLES_PATH, "\n".join(preserved))
    return True

def _parse_startup_apps() -> list[dict]:
    text = _read_text(STARTUP_APPS_PATH)
    apps = []
    system_tokens = [
        "dbus-update-activation-environment",
        "systemctl --user import-environment",
        "xdg-desktop-portal-hyprland",
        "xdg-desktop-portal-gtk",
        "Polkit.sh",
        "PortalRestart.sh",
        "StartQuickshell.sh",
        "PowerProfileAuto.sh",
        "waybar",
        "hypridle",
        "wl-paste",
        "pkill firefox",
    ]
    for idx, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not stripped.startswith("exec-once"):
            continue
        cmd = stripped.split("=", 1)[1].strip() if "=" in stripped else ""
        if not cmd:
            continue
        is_system = any(token in cmd for token in system_tokens)
        apps.append({"index": idx, "cmd": cmd, "enabled": True, "system": is_system})
    return apps

def _sync_startup_apps(apps: list[dict]) -> bool:
    text = _read_text(STARTUP_APPS_PATH)
    if not text:
        return False
    out_lines = text.splitlines()
    changed = False
    for app in apps:
        idx = app.get("index")
        if idx is None or idx < 0 or idx >= len(out_lines):
            continue
        prefix = "" if app.get("enabled", True) else "# "
        new_line = f"{prefix}exec-once = {app['cmd']}"
        if out_lines[idx] != new_line:
            out_lines[idx] = new_line
            changed = True
    if changed:
        _write_text(STARTUP_APPS_PATH, "\n".join(out_lines))
    return changed

def _parse_workspace_rules() -> list[dict]:
    text = _read_text(WINDOW_RULES_PATH)
    rules = []
    for idx, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("windowrule"):
            continue
        if "workspace" not in stripped or "match:class" not in stripped and "match:tag" not in stripped:
            continue
        match = re.search(r'workspace\s+([^,\s]+)(?:\s+(silent))?,\s*match:(?:class|tag)\s+(.+)$', stripped)
        if not match:
            continue
        workspace = match.group(1).strip()
        modifier = match.group(2).strip() if match.group(2) else ""
        selector = match.group(3).strip()
        rules.append({"index": idx, "workspace": workspace, "modifier": modifier, "selector": selector, "line": line})
    return rules

def _sync_workspace_rules(rules: list[dict]) -> bool:
    text = _read_text(WINDOW_RULES_PATH)
    if not text:
        return False
    out_lines = text.splitlines()
    changed = False
    for rule in rules:
        idx = rule.get("index")
        if idx is None or idx < 0 or idx >= len(out_lines):
            continue
        line = out_lines[idx]
        workspace = str(rule.get("workspace", "1")).strip() or "1"
        modifier = str(rule.get("modifier", "")).strip()
        selector = str(rule.get("selector", "")).strip()
        if not selector:
            continue
        if "match:tag" in line:
            suffix = f" {modifier}" if modifier else ""
            new_line = re.sub(r'workspace\s+[^,]+,\s*match:tag\s+.+$', f'workspace {workspace}{suffix}, match:tag {selector}', line)
        else:
            suffix = f" {modifier}" if modifier else ""
            new_line = re.sub(r'workspace\s+[^,]+,\s*match:class\s+.+$', f'workspace {workspace}{suffix}, match:class {selector}', line)
        if new_line != line:
            out_lines[idx] = new_line
            changed = True
    if changed:
        _write_text(WINDOW_RULES_PATH, "\n".join(out_lines))
    return changed


# ── Window ────────────────────────────────────────────────────────────────────

PAGES = [
    ("General",      "preferences-system-symbolic"),
    ("Screen",       "video-display-symbolic"),
    ("Components",   "view-app-grid-symbolic"),
    ("Power",        "battery-symbolic"),
    ("Clock",        "preferences-system-time-symbolic"),
    ("Hypridle",     "preferences-system-time-symbolic"),
    ("Integrations", "applications-engineering-symbolic"),
    ("Apps",         "applications-symbolic"),
    ("Intervals",    "preferences-system-time-symbolic"),
    ("Startup Apps", "system-run-symbolic"),
    ("Window Rules", "window-symbolic"),
    ("Keybinds",     "input-keyboard-symbolic"),
]


class ConfigWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_default_size(1020, 740)
        self.set_size_request(760, 520)
        self.set_title("SdrxDots Settings")
        self.set_icon_name("preferences-system-symbolic")
        self.add_css_class("config-panel")

        # Sync wallpaper state with reality on open
        subprocess.run([sys.executable, str(HOME / ".config/quickshell/scripts/python/wallpaper_sync.py")], check=False)

        self._config = load_json(CONFIG_PATH)
        self._skwd_wall_config = load_json(SKWD_WALL_CONFIG_PATH)
        if get_nested(self._config, ["hypridle", "enabled"], None) is None:
            set_nested(self._config, ["hypridle", "enabled"], True)
        if get_nested(self._config, ["hypridle", "warnMinutes"], None) is None:
            set_nested(self._config, ["hypridle", "warnMinutes"], 9)
        if get_nested(self._config, ["hypridle", "lockMinutes"], None) is None:
            set_nested(self._config, ["hypridle", "lockMinutes"], 10)
        if get_nested(self._config, ["hypridle", "ignoreDbusInhibit"], None) is None:
            set_nested(self._config, ["hypridle", "ignoreDbusInhibit"], False)
        if get_nested(self._config, ["appearance", "colorMode"], None) is None:
            set_nested(self._config, ["appearance", "colorMode"], _read_theme_mode())
        self._apps   = load_json(APPS_PATH)
        self._positions = load_json(POSITIONS_JSON_PATH)
        self._migrate_positions_to_extensions()
        self._defaults_config = deepcopy(self._config)
        self._defaults_skwd_wall_config = deepcopy(self._skwd_wall_config)
        self._defaults_apps   = deepcopy(self._apps)
        self._defaults_positions = deepcopy(self._positions)
        self._saved_config    = deepcopy(self._config)
        self._saved_skwd_wall_config = deepcopy(self._skwd_wall_config)
        self._saved_apps      = deepcopy(self._apps)
        self._saved_positions = deepcopy(self._positions)
        self._unsaved = False
        self._ensure_valid_monitor()

        self._selected_terminal = _read_userdefaults_terminal()
        self._selected_shell = _read_userdefaults_shell()
        self._selected_compositor = _read_compositor()
        self._selected_gpu_vendor = _read_gpu_vendor()
        self._selected_color_mode = str(get_nested(self._config, ["appearance", "colorMode"], _read_theme_mode()) or "dark")
        self._startup_apps = _parse_startup_apps()
        self._startup_show_system = False
        self._workspace_rules = _parse_workspace_rules()

        self._keybinds_system_lines: list[str] = []
        self._keybinds_user_lines:   list[str] = []
        self._keybinds_launcher_lines: list[str] = []
        self._keybinds_all:   list[dict] = []
        self._keybinds_saved: list[dict] = []
        self._external_conflict_paths: list[str] = []
        self._suppress_external_reload_until = 0.0
        self._file_mtimes: dict[str, float | None] = {}
        self._built_pages: set[str] = set()
        self._load_keybinds()

        self._build_ui()
        self._install_css()
        self._apply_color_mode_style()
        self._setup_file_monitor()
        self._setup_shortcuts()
        self._update_title()

    # ── UI skeleton ───────────────────────────────────────────────────────────

    def _build_ui(self):
        toolbar_view = Adw.ToolbarView()

        # Header bar
        header_bar = Adw.HeaderBar()
        header_bar.set_show_title(True)

        self._save_btn    = Gtk.Button(label="Save")
        self._discard_btn = Gtk.Button(label="Discard")
        self._defaults_btn = Gtk.Button(label="Defaults")
        self._save_btn.add_css_class("suggested-action")
        self._discard_btn.add_css_class("destructive-action")
        self._save_btn.set_sensitive(False)
        self._discard_btn.set_sensitive(False)
        self._save_btn.connect("clicked", self._on_save)
        self._discard_btn.connect("clicked", self._on_discard)
        self._defaults_btn.connect("clicked", self._on_defaults)

        header_bar.pack_end(self._save_btn)
        header_bar.pack_end(self._discard_btn)
        header_bar.pack_start(self._defaults_btn)
        toolbar_view.add_top_bar(header_bar)

        # Unsaved banner
        self._banner = Adw.Banner(title="Unsaved changes")
        self._banner.set_button_label("Save now")
        self._banner.connect("button-clicked", self._on_save)
        toolbar_view.add_top_bar(self._banner)

        self._reload_banner = Adw.Banner(title="External changes detected")
        self._reload_banner.set_button_label("Reload now")
        self._reload_banner.connect("button-clicked", self._on_reload_external)
        toolbar_view.add_top_bar(self._reload_banner)

        # Split view: sidebar left, content right
        split = Adw.OverlaySplitView()
        split.set_sidebar_width_fraction(0.22)
        split.set_min_sidebar_width(180)
        split.set_max_sidebar_width(260)
        split.set_collapsed(False)
        split.set_show_sidebar(True)

        split.set_sidebar(self._build_sidebar())

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(180)
        self._stack.set_vexpand(True)
        self._stack.set_hexpand(True)

        self._page_builders = [
            self._build_general_page,
            self._build_screen_page,
            self._build_components_page,
            self._build_power_page,
            self._build_clock_page,
            self._build_hypridle_page,
            self._build_integrations_page,
            self._build_apps_page,
            self._build_intervals_page,
            self._build_startup_apps_page,
            self._build_window_rules_page,
            self._build_keybinds_page,
        ]

        # Build pages lazily to keep startup responsive.
        self._page_builder_map = {
            name.lower(): self._page_builders[i]
            for i, (name, _icon) in enumerate(PAGES)
        }

        split.set_content(self._stack)
        toolbar_view.set_content(split)

        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(toolbar_view)
        self.set_content(self._toast_overlay)
        first_page = PAGES[0][0].lower()
        self._ensure_page(first_page)
        self._nav_list.select_row(self._nav_list.get_row_at_index(0))
        self._banner.set_revealed(False)
        self._reload_banner.set_revealed(False)

    def _ensure_page(self, page_name: str):
        if page_name in self._built_pages:
            return
        builder = self._page_builder_map.get(page_name)
        if builder is None:
            return
        page_widget = builder()
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(page_widget)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._stack.add_named(scroll, page_name)
        self._built_pages.add(page_name)

    def _build_sidebar(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("navigation-sidebar")

        # Search bar
        self._search_entry = Gtk.SearchEntry(placeholder_text="Search…")
        self._search_entry.set_margin_start(8)
        self._search_entry.set_margin_end(8)
        self._search_entry.set_margin_top(10)
        self._search_entry.set_margin_bottom(6)
        self._search_entry.connect("search-changed", self._on_global_search)
        box.append(self._search_entry)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_bottom(4)
        box.append(sep)

        self._nav_list = Gtk.ListBox()
        self._nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._nav_list.add_css_class("navigation-sidebar")
        self._nav_list.set_vexpand(True)
        self._nav_list.connect("row-selected", self._on_nav_select)

        for name, icon in PAGES:
            row = Gtk.ListBoxRow()
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            hbox.set_margin_start(12)
            hbox.set_margin_end(12)
            hbox.set_margin_top(8)
            hbox.set_margin_bottom(8)
            img = Gtk.Image.new_from_icon_name(icon)
            img.set_pixel_size(16)
            lbl = Gtk.Label(label=name, xalign=0.0, hexpand=True)
            hbox.append(img)
            hbox.append(lbl)
            row.set_child(hbox)
            self._nav_list.append(row)

        box.append(self._nav_list)
        return box

    def _on_nav_select(self, listbox, row):
        if row is None or not hasattr(self, "_stack"):
            return
        idx = row.get_index()
        if 0 <= idx < len(PAGES):
            page_name = PAGES[idx][0].lower()
            self._ensure_page(page_name)
            self._stack.set_visible_child_name(page_name)

    def _on_global_search(self, entry):
        query = entry.get_text().strip().lower()
        if not query:
            return
        # Jump to first page whose name matches
        for i, (name, _) in enumerate(PAGES):
            if query in name.lower():
                self._nav_list.select_row(self._nav_list.get_row_at_index(i))
                return

    # ── Unsaved state ─────────────────────────────────────────────────────────

    def _mark_unsaved(self):
        if not self._unsaved:
            self._unsaved = True
            self._save_btn.set_sensitive(True)
            self._discard_btn.set_sensitive(True)
            self._banner.set_revealed(True)
            self._update_title()

    def _mark_saved(self):
        self._unsaved = False
        self._save_btn.set_sensitive(False)
        self._discard_btn.set_sensitive(False)
        self._banner.set_revealed(False)
        self._update_title()

    def _apply_color_mode_style(self):
        self.remove_css_class("system-dark")
        self.remove_css_class("system-light")
        if (self._selected_color_mode or "dark").strip().lower() == "light":
            self.add_css_class("system-light")
        else:
            self.add_css_class("system-dark")

    # ── Keyboard shortcuts ────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.GLOBAL)

        trigger = Gtk.ShortcutTrigger.parse_string("<Ctrl>s")
        if trigger is not None:
            save_sc = Gtk.Shortcut(
                trigger=trigger,
                action=Gtk.CallbackAction.new(lambda *_: self._on_save(None) or True),
            )
            ctrl.add_shortcut(save_sc)

        esc_trigger = Gtk.ShortcutTrigger.parse_string("Escape")
        if esc_trigger is not None:
            close_sc = Gtk.Shortcut(
                trigger=esc_trigger,
                action=Gtk.CallbackAction.new(lambda *_: self.close() or True),
            )
            ctrl.add_shortcut(close_sc)
        self.add_controller(ctrl)

    # ── File monitor ──────────────────────────────────────────────────────────

    def _setup_file_monitor(self):
        self._file_mtimes = self._snapshot_file_mtimes()
        GLib.timeout_add(1500, self._poll_external_changes)

    def _tracked_files(self) -> dict[str, Path]:
        return {
            "config.json": CONFIG_PATH,
            "apps.json": APPS_PATH,
            "Keybinds.conf": KEYBINDS_SYSTEM_PATH,
            "UserKeybinds.conf": KEYBINDS_USER_PATH,
            "UserLauncherBinds.conf": KEYBINDS_LAUNCHER_PATH,
            "01-UserDefaults.conf": USER_DEFAULTS_PATH,
            "ENVariables.conf": ENV_VARIABLES_PATH,
            "Startup_Apps.conf": STARTUP_APPS_PATH,
            "WindowRules.conf": WINDOW_RULES_PATH,
            "hypridle.conf": HYPRIDLE_CONF_PATH,
            "positions.json": POSITIONS_JSON_PATH,
        }

    def _mtime(self, path: Path) -> float | None:
        try:
            return path.stat().st_mtime
        except FileNotFoundError:
            return None

    def _snapshot_file_mtimes(self) -> dict[str, float | None]:
        return {name: self._mtime(path) for name, path in self._tracked_files().items()}

    def _poll_external_changes(self):
        now = time.time()
        current = self._snapshot_file_mtimes()
        if now < self._suppress_external_reload_until:
            self._file_mtimes = current
            return True

        changed = [
            name for name, mtime in current.items()
            if mtime != self._file_mtimes.get(name)
        ]
        if changed:
            if self._unsaved:
                self._external_conflict_paths = changed
                self._reload_banner.set_title(
                    "External changes in " + ", ".join(changed) + ". Reload to discard local edits."
                )
                self._reload_banner.set_revealed(True)
            else:
                self._reload_from_disk(changed)
        self._file_mtimes = current
        return True

    def _reload_from_disk(self, changed: list[str] | None = None):
        self._config = load_json(CONFIG_PATH)
        self._skwd_wall_config = load_json(SKWD_WALL_CONFIG_PATH)
        self._apps = load_json(APPS_PATH)
        self._positions = load_json(POSITIONS_JSON_PATH)
        self._ensure_valid_monitor()
        self._load_keybinds()
        self._selected_terminal = _read_userdefaults_terminal()
        self._selected_shell = _read_userdefaults_shell()
        self._selected_compositor = _read_compositor()
        self._selected_gpu_vendor = _read_gpu_vendor()
        self._selected_color_mode = str(get_nested(self._config, ["appearance", "colorMode"], _read_theme_mode()) or "dark")
        self._startup_apps = _parse_startup_apps()
        self._workspace_rules = _parse_workspace_rules()
        self._apply_color_mode_style()
        self._saved_config = deepcopy(self._config)
        self._saved_skwd_wall_config = deepcopy(self._skwd_wall_config)
        self._saved_apps = deepcopy(self._apps)
        self._saved_positions = deepcopy(self._positions)
        self._mark_saved()
        self._reload_banner.set_revealed(False)
        self._external_conflict_paths = []
        self._refresh_pages()
        if changed:
            self._toast("Reloaded external changes: " + ", ".join(changed))

    # ── Save / Discard / Defaults ─────────────────────────────────────────────

    def _on_save(self, _widget):
        prev_bar    = get_nested(self._saved_config, ["components", "bar", "enabled"], True)
        prev_cfg_raw = get_nested(self._saved_config, ["components", "bar", "waybarConfig"], "~/.config/waybar/config")
        prev_sty_raw = get_nested(self._saved_config, ["components", "bar", "waybarStyle"], "~/.config/waybar/style.css")
        prev_pow_t  = get_nested(self._saved_config, ["power", "deviceType"], "auto")
        prev_pow_p  = get_nested(self._saved_config, ["power", "profile"], "performance")
        prev_opt    = bool(get_nested(self._saved_config, ["optimization", "enabled"], False))
        prev_visual_toggles = _visual_toggles_from_config(self._saved_config)
        prev_idle_enabled = bool(get_nested(self._saved_config, ["hypridle", "enabled"], True))
        prev_idle_warn = int(get_nested(self._saved_config, ["hypridle", "warnMinutes"], 9) or 9)
        prev_idle_lock = int(get_nested(self._saved_config, ["hypridle", "lockMinutes"], 10) or 10)
        prev_idle_ignore = bool(get_nested(self._saved_config, ["hypridle", "ignoreDbusInhibit"], False))

        cur_opt_enabled = bool(get_nested(self._config, ["optimization", "enabled"], False))
        _apply_optimization_component_mode(self._config, cur_opt_enabled)

        self._normalize_apps_data()
        save_json(CONFIG_PATH, self._config)
        save_json(SKWD_WALL_CONFIG_PATH, self._skwd_wall_config)
        save_json(APPS_PATH, self._apps)
        save_json(POSITIONS_JSON_PATH, self._positions)

        cur_bar = get_nested(self._config, ["components", "bar", "enabled"], True)
        cur_cfg_raw = get_nested(self._config, ["components", "bar", "waybarConfig"], "~/.config/waybar/config")
        cur_sty_raw = get_nested(self._config, ["components", "bar", "waybarStyle"], "~/.config/waybar/style.css")
        prev_cfg = str(Path(str(prev_cfg_raw).replace("~", str(HOME))))
        prev_sty = str(Path(str(prev_sty_raw).replace("~", str(HOME))))
        cur_cfg = str(Path(str(cur_cfg_raw).replace("~", str(HOME))))
        cur_sty = str(Path(str(cur_sty_raw).replace("~", str(HOME))))
        bar_paths_changed = (cur_cfg != prev_cfg) or (cur_sty != prev_sty)

        # Keep ~/.config/waybar/config and style.css aligned so external refresh scripts
        # (e.g. Win+Alt+R Refresh.sh) preserve the selected preset.
        sync_waybar_links(cur_cfg, cur_sty)

        if cur_bar != prev_bar:
            ok = apply_waybar(cur_bar, cur_cfg, cur_sty, restart=cur_bar)
            if cur_bar and not ok:
                set_nested(self._config, ["components", "bar", "waybarConfig"], prev_cfg_raw)
                set_nested(self._config, ["components", "bar", "waybarStyle"], prev_sty_raw)
                sync_waybar_links(prev_cfg, prev_sty)
                apply_waybar(True, prev_cfg, prev_sty, restart=True)
                save_json(CONFIG_PATH, self._config)
                reason = _waybar_last_error_summary(style_path=cur_sty)
                style_name = Path(cur_sty).name
                msg = f"Waybar failed for {style_name}; restored previous working style"
                if reason:
                    msg += f" ({reason})"
                self._toast(msg, timeout=4)
        elif cur_bar and bar_paths_changed:
            ok = apply_waybar(True, cur_cfg, cur_sty, restart=True)
            if not ok:
                set_nested(self._config, ["components", "bar", "waybarConfig"], prev_cfg_raw)
                set_nested(self._config, ["components", "bar", "waybarStyle"], prev_sty_raw)
                sync_waybar_links(prev_cfg, prev_sty)
                apply_waybar(True, prev_cfg, prev_sty, restart=True)
                save_json(CONFIG_PATH, self._config)
                reason = _waybar_last_error_summary(style_path=cur_sty)
                style_name = Path(cur_sty).name
                msg = f"Selected style failed: {style_name}; reverted to previous working style"
                if reason:
                    msg += f" ({reason})"
                self._toast(msg, timeout=4)

        if (get_nested(self._config, ["power", "deviceType"], "auto") != prev_pow_t or
                get_nested(self._config, ["power", "profile"], "performance") != prev_pow_p):
            apply_power_profile()

        cur_opt = bool(get_nested(self._config, ["optimization", "enabled"], False))
        cur_visual_toggles = _visual_toggles_from_config(self._config)
        
        # Track if we need to reload Hyprland or reapply optimizations
        hypr_conf_changed = False

        if _sync_userdefaults_terminal(self._selected_terminal):
            self._toast(f"Terminal set to {self._selected_terminal}")
            hypr_conf_changed = True

        if _sync_userdefaults_shell(self._selected_shell):
            self._toast(f"Shell set to {self._selected_shell}")
            hypr_conf_changed = True

        cur_monitors = get_nested(self._config, ["monitors_list"], [])
        if not cur_monitors:
             cur_monitors = [str(get_nested(self._config, ["monitor"], "auto")),
                             str(get_nested(self._config, ["secondary_monitor"], "auto"))]
                             
        secondary_bar_enabled = bool(get_nested(self._config, ["components", "bar", "secondaryBarEnabled"], True))
        prev_secondary_bar_enabled = bool(get_nested(self._saved_config, ["components", "bar", "secondaryBarEnabled"], True))

        monitors_changed = _sync_userdefaults_monitors(cur_monitors)
        secondary_bar_changed = secondary_bar_enabled != prev_secondary_bar_enabled

        if monitors_changed or secondary_bar_changed:
            if monitors_changed:
                self._toast(f"Monitors updated: {', '.join(cur_monitors)}")
                hypr_conf_changed = True
            _sync_waybar_monitors(cur_monitors, secondary_bar_enabled)
            _sync_workspaces_conf(cur_monitors)
            hypr_conf_changed = True

        if _sync_envariables_gpu(self._selected_gpu_vendor):
            self._toast(f"GPU preset set to {self._selected_gpu_vendor}")
            hypr_conf_changed = True

        if _sync_theme_mode(self._selected_color_mode):
            self._toast(f"System color mode set to {self._selected_color_mode}")
            # Theme mode change usually affects GTK/QT, but might be linked to Hyprland configs too
            hypr_conf_changed = True 
        self._apply_color_mode_style()

        if self._startup_apps:
            if _sync_startup_apps(self._startup_apps):
                hypr_conf_changed = True

        workspace_rules_changed = False
        if self._workspace_rules:
            workspace_rules_changed = _sync_workspace_rules(self._workspace_rules)
        if workspace_rules_changed:
            hypr_conf_changed = True

        cur_idle_enabled = bool(get_nested(self._config, ["hypridle", "enabled"], True))
        cur_idle_warn = max(1, int(get_nested(self._config, ["hypridle", "warnMinutes"], 9) or 9))
        cur_idle_lock = max(1, int(get_nested(self._config, ["hypridle", "lockMinutes"], 10) or 10))
        cur_idle_ignore = bool(get_nested(self._config, ["hypridle", "ignoreDbusInhibit"], False))

        if cur_idle_warn >= cur_idle_lock:
            cur_idle_lock = cur_idle_warn + 1
            set_nested(self._config, ["hypridle", "lockMinutes"], cur_idle_lock)
            save_json(CONFIG_PATH, self._config)
            self._toast("Hypridle lock timeout adjusted to stay after warning")

        idle_changed = (
            cur_idle_enabled != prev_idle_enabled
            or cur_idle_warn != prev_idle_warn
            or cur_idle_lock != prev_idle_lock
            or cur_idle_ignore != prev_idle_ignore
        )

        if idle_changed:
            sync_hypridle_conf(
                warn_seconds=cur_idle_warn * 60,
                lock_seconds=cur_idle_lock * 60,
                ignore_dbus_inhibit=cur_idle_ignore,
            )
            apply_hypridle_enabled(cur_idle_enabled)

        keybinds_changed = False
        if self._keybinds_all != self._keybinds_saved:
            sys_binds = [b for b in self._keybinds_all if b["source"] == "SYSTEM"]
            usr_binds = [b for b in self._keybinds_all if b["source"] == "USER"]
            lnch_binds = [b for b in self._keybinds_all if b["source"] == "LAUNCHER"]
            KEYBINDS_SYSTEM_PATH.write_text(rebuild_keybind_file(self._keybinds_system_lines, sys_binds))
            KEYBINDS_USER_PATH.write_text(rebuild_keybind_file(self._keybinds_user_lines, usr_binds))
            KEYBINDS_LAUNCHER_PATH.write_text(rebuild_keybind_file(self._keybinds_launcher_lines, lnch_binds))
            self._keybinds_saved = deepcopy(self._keybinds_all)
            keybinds_changed = True
            hypr_conf_changed = True

        # Finally, handle Hyprland reload and optimizations
        if hypr_conf_changed:
            # This will trigger a reload and re-apply optimizations after a delay
            apply_hypr_reload()
        elif cur_visual_toggles != prev_visual_toggles:
            # If no reload is needed but toggles changed, apply them immediately
            apply_visual_toggles(self._config)

        if cur_opt != prev_opt and cur_opt:
                self._toast("Optimization mode active: only wallpapers remain enabled")

        self._saved_config = deepcopy(self._config)
        self._saved_skwd_wall_config = deepcopy(self._skwd_wall_config)
        self._saved_apps   = deepcopy(self._apps)
        self._saved_positions = deepcopy(self._positions)
        self._suppress_external_reload_until = time.time() + 1.2
        self._mark_saved()
        self._reload_banner.set_revealed(False)
        self._external_conflict_paths = []

        self._toast("Settings saved")

    def _on_discard(self, _widget):
        self._config = deepcopy(self._saved_config)
        self._skwd_wall_config = deepcopy(self._saved_skwd_wall_config)
        self._apps   = deepcopy(self._saved_apps)
        self._positions = deepcopy(self._saved_positions)
        self._keybinds_all = deepcopy(self._keybinds_saved)
        self._selected_terminal = _read_userdefaults_terminal()
        self._selected_shell = _read_userdefaults_shell()
        self._selected_compositor = _read_compositor()
        self._selected_gpu_vendor = _read_gpu_vendor()
        self._selected_color_mode = str(get_nested(self._config, ["appearance", "colorMode"], _read_theme_mode()) or "dark")
        self._startup_apps = _parse_startup_apps()
        self._workspace_rules = _parse_workspace_rules()
        self._apply_color_mode_style()
        self._mark_saved()
        self._reload_banner.set_revealed(False)
        self._external_conflict_paths = []
        self._refresh_pages()

    def _on_defaults(self, _widget):
        self._config = deepcopy(self._defaults_config)
        self._skwd_wall_config = deepcopy(self._defaults_skwd_wall_config)
        self._apps   = deepcopy(self._defaults_apps)
        self._positions = deepcopy(self._defaults_positions)
        self._selected_terminal = _read_userdefaults_terminal()
        self._selected_shell = _read_userdefaults_shell()
        self._selected_compositor = _read_compositor()
        self._selected_gpu_vendor = _read_gpu_vendor()
        self._selected_color_mode = str(get_nested(self._config, ["appearance", "colorMode"], _read_theme_mode()) or "dark")
        self._startup_apps = _parse_startup_apps()
        self._workspace_rules = _parse_workspace_rules()
        self._apply_color_mode_style()
        self._apply_color_mode_style()
        self._mark_unsaved()
        self._refresh_pages()

    def _on_reload_external(self, _widget):
        self._reload_from_disk(self._external_conflict_paths)

    def _update_title(self):
        self.set_title("SdrxDots Settings*" if self._unsaved else "SdrxDots Settings")

    def _toast(self, text: str, timeout: int = 2):
        self._toast_overlay.add_toast(Adw.Toast(title=text, timeout=timeout))

    def _install_css(self):
        css = b"""
        window.config-panel.system-dark {
            background: #1b1b1f;
            color: #e3e3e7;
        }

        window.config-panel.system-light {
            background: @view_bg_color;
            color: @view_fg_color;
        }

        window.config-panel.system-dark .navigation-sidebar {
            background: #232329;
            border-right: 1px solid #2e2f36;
        }

        window.config-panel.system-light .navigation-sidebar {
            border-right: 1px solid alpha(@view_fg_color, 0.10);
        }

        window.config-panel.system-dark preferencespage,
        window.config-panel.system-dark preferencesgroup,
        window.config-panel.system-dark preferencesgroup > box,
        window.config-panel.system-dark list,
        window.config-panel.system-dark row,
        window.config-panel.system-dark entry,
        window.config-panel.system-dark textview {
            background: #202126;
            color: #e3e3e7;
            border-color: #32333a;
        }

        window.config-panel.system-dark row:hover,
        window.config-panel.system-dark .navigation-sidebar row:hover {
            background: #2a2b33;
        }

        window.config-panel.system-dark .navigation-sidebar row:selected {
            background: #323441;
            color: #f2f2f4;
        }

        .navigation-sidebar {
            border-right: 1px solid alpha(@window_fg_color, 0.08);
        }

        .dim-label {
            opacity: 0.7;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _normalize_apps_data(self):
        for app_key, app_data in self._apps.items():
            if app_key.startswith("_") or not isinstance(app_data, dict):
                continue
            tags = app_data.get("tags")
            if isinstance(tags, str):
                app_data["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

    def _refresh_pages(self):
        current = self._stack.get_visible_child_name() or PAGES[0][0].lower()
        # Remove all pages and invalidate cache; current page is rebuilt lazily.
        for name, _ in PAGES:
            child = self._stack.get_child_by_name(name.lower())
            if child:
                self._stack.remove(child)
        self._built_pages.clear()
        self._ensure_page(current)
        self._stack.set_visible_child_name(current)

    # ── Keybinds ──────────────────────────────────────────────────────────────

    def _load_keybinds(self):
        sys_text = KEYBINDS_SYSTEM_PATH.read_text() if KEYBINDS_SYSTEM_PATH.exists() else ""
        usr_text = KEYBINDS_USER_PATH.read_text()   if KEYBINDS_USER_PATH.exists()   else ""
        lnch_text = KEYBINDS_LAUNCHER_PATH.read_text() if KEYBINDS_LAUNCHER_PATH.exists() else ""
        self._keybinds_system_lines = sys_text.splitlines()
        self._keybinds_user_lines   = usr_text.splitlines()
        self._keybinds_launcher_lines = lnch_text.splitlines()
        self._keybinds_all   = _parse_keybinds(sys_text, "SYSTEM") + _parse_keybinds(usr_text, "USER") + _parse_keybinds(lnch_text, "LAUNCHER")
        self._keybinds_saved = deepcopy(self._keybinds_all)

    def _ensure_valid_monitor(self):
        detected = _detect_monitors()
        if not detected or detected == ["auto"]:
            return

        mlist = get_nested(self._config, ["monitors_list"], [])
        if not mlist:
            mlist = [str(get_nested(self._config, ["monitor"], "")),
                     str(get_nested(self._config, ["secondary_monitor"], ""))]
        
        changed = False
        new_list = []
        for i, m in enumerate(mlist):
            if not m: continue
            if m in detected or m == "auto":
                new_list.append(m)
            else:
                # Fallback: if it's the primary and not found, pick first detected
                if i == 0:
                    new_list.append(detected[0])
                    changed = True
                else:
                    # For secondary+, just remove or set to auto if we want to keep slots
                    # Let's just set to auto
                    new_list.append("auto")
                    changed = True

        if changed:
            set_nested(self._config, ["monitors_list"], new_list)
            # Compatibility
            set_nested(self._config, ["monitor"], new_list[0])
            if len(new_list) > 1:
                set_nested(self._config, ["secondary_monitor"], new_list[1])
                
            save_json(CONFIG_PATH, self._config)
            _sync_userdefaults_monitors(new_list)

    # ── Row builders ──────────────────────────────────────────────────────────

    def _entry_row(self, title: str, keys: list[str], config_src=None) -> Adw.EntryRow:
        row = Adw.EntryRow(title=title)
        cfg = config_src if config_src is not None else self._config
        val = get_nested(cfg, keys, "")
        row.set_text(str(val) if val else "")
        def on_changed(r, k=keys, c=cfg):
            set_nested(c, k, r.get_text())
            self._mark_unsaved()
        row.connect("changed", on_changed)
        return row

    def _switch_row(self, title: str, keys: list[str], subtitle: str = "", config_src=None) -> Adw.SwitchRow:
        row = Adw.SwitchRow(title=title)
        if subtitle:
            row.set_subtitle(subtitle)
        cfg = config_src if config_src is not None else self._config
        row.set_active(bool(get_nested(cfg, keys, False)))
        def on_toggle(r, _p, k=keys, c=cfg):
            set_nested(c, k, r.get_active())
            self._mark_unsaved()
        row.connect("notify::active", on_toggle)
        return row

    def _combo_row(self, title: str, keys: list[str], choices: list[str], config_src=None) -> Adw.ComboRow:
        row = Adw.ComboRow(title=title)
        store = Gtk.StringList()
        for c in choices:
            store.append(c)
        row.set_model(store)
        cfg = config_src if config_src is not None else self._config
        val = get_nested(cfg, keys, choices[0] if choices else "")
        if val in choices:
            row.set_selected(choices.index(val))
        def on_changed(r, _p, k=keys, ch=choices, c=cfg):
            idx = r.get_selected()
            if 0 <= idx < len(ch):
                set_nested(c, k, ch[idx])
                self._mark_unsaved()
        row.connect("notify::selected", on_changed)
        return row

    def _spin_row(self, title: str, keys: list[str],
                  min_val=0, max_val=9_999_999, step=1, subtitle: str = "", config_src=None) -> Adw.SpinRow:
        cfg = config_src if config_src is not None else self._config
        adj = Gtk.Adjustment(
            value=float(get_nested(cfg, keys, 0) or 0),
            lower=min_val, upper=max_val, step_increment=step,
        )
        row = Adw.SpinRow(title=title, adjustment=adj)
        if subtitle:
            row.set_subtitle(subtitle)
        def on_changed(r, k=keys, c=cfg):
            set_nested(c, k, int(r.get_value()))
            self._mark_unsaved()
        row.connect("changed", on_changed)
        return row

    def _combo_row_direct(self, title: str, choices: list[str], current: str,
                          on_change, subtitle: str = "") -> Adw.ComboRow:
        row = Adw.ComboRow(title=title)
        if subtitle:
            row.set_subtitle(subtitle)

        if not choices:
            choices = ["No options found"]
            row.set_sensitive(False)

        store = Gtk.StringList()
        for c in choices:
            store.append(c)
        row.set_model(store)

        selected = 0
        if current in choices:
            selected = choices.index(current)
        row.set_selected(selected)

        def on_selected(r, _p, ch=choices):
            idx = r.get_selected()
            if 0 <= idx < len(ch):
                on_change(ch[idx])
                self._mark_unsaved()

        row.connect("notify::selected", on_selected)
        return row

    def _wallpaper_display_mode(self) -> str:
        mode = str(get_nested(self._skwd_wall_config, ["components", "wallpaperSelector", "displayMode"], "slices") or "slices")
        aliases = {
            "slice": "slices",
            "grid": "wall",
            "list": "wall",
        }
        return aliases.get(mode, mode if mode in ("slices", "hex", "wall") else "slices")

    def _wallpaper_size_presets(self, mode: str) -> dict[str, dict]:
        if mode == "hex":
            return {
                "XS": {"hexRadius": 70,  "hexRows": 1, "hexCols": 5, "hexScrollStep": 1, "hexArc": True, "hexArcIntensity": 0.8},
                "S":  {"hexRadius": 90,  "hexRows": 1, "hexCols": 6, "hexScrollStep": 1, "hexArc": True, "hexArcIntensity": 1.0},
                "M":  {"hexRadius": 115, "hexRows": 2, "hexCols": 7, "hexScrollStep": 1, "hexArc": True, "hexArcIntensity": 1.2},
                "L":  {"hexRadius": 140, "hexRows": 2, "hexCols": 7, "hexScrollStep": 1, "hexArc": True, "hexArcIntensity": 1.2},
                "XL": {"hexRadius": 170, "hexRows": 3, "hexCols": 8, "hexScrollStep": 1, "hexArc": True, "hexArcIntensity": 1.3},
            }
        if mode == "wall":
            return {
                "XS": {"gridColumns": 7, "gridRows": 3, "gridThumbWidth": 160, "gridThumbHeight": 90},
                "S":  {"gridColumns": 6, "gridRows": 3, "gridThumbWidth": 220, "gridThumbHeight": 124},
                "M":  {"gridColumns": 5, "gridRows": 3, "gridThumbWidth": 280, "gridThumbHeight": 158},
                "L":  {"gridColumns": 4, "gridRows": 3, "gridThumbWidth": 340, "gridThumbHeight": 191},
                "XL": {"gridColumns": 3, "gridRows": 2, "gridThumbWidth": 460, "gridThumbHeight": 259},
            }
        return {
            "XS": {"expandedWidth": 360,  "sliceHeight": 200, "sliceWidth": 52,  "visibleCount": 20, "sliceSpacing": -30, "skewOffset": 16},
            "S":  {"expandedWidth": 480,  "sliceHeight": 270, "sliceWidth": 68,  "visibleCount": 18, "sliceSpacing": -30, "skewOffset": 20},
            "M":  {"expandedWidth": 768,  "sliceHeight": 432, "sliceWidth": 108, "visibleCount": 14, "sliceSpacing": -30, "skewOffset": 28},
            "L":  {"expandedWidth": 924,  "sliceHeight": 520, "sliceWidth": 135, "visibleCount": 12, "sliceSpacing": -30, "skewOffset": 35},
            "XL": {"expandedWidth": 1280, "sliceHeight": 720, "sliceWidth": 180, "visibleCount": 9,  "sliceSpacing": -30, "skewOffset": 45},
        }

    def _wallpaper_preset_label_for_current(self, mode: str) -> str:
        selector = get_nested(self._skwd_wall_config, ["components", "wallpaperSelector"], {})
        for label, fields in self._wallpaper_size_presets(mode).items():
            if all(selector.get(k) == v for k, v in fields.items() if k != "activeCustomPreset"):
                return label
        return "Custom"

    def _wallpaper_size_preset_row(self) -> Adw.ComboRow:
        mode = self._wallpaper_display_mode()
        choices = ["XS", "S", "M", "L", "XL", "Custom"]
        current = self._wallpaper_preset_label_for_current(mode)

        def on_change(choice: str):
            if choice == "Custom":
                return
            selector_path = ["components", "wallpaperSelector"]
            set_nested(self._skwd_wall_config, selector_path + ["displayMode"], self._wallpaper_display_mode())
            for key, value in self._wallpaper_size_presets(self._wallpaper_display_mode())[choice].items():
                set_nested(self._skwd_wall_config, selector_path + [key], value)
            set_nested(self._skwd_wall_config, selector_path + ["activeCustomPreset"], "")

        return self._combo_row_direct(
            "Selector size preset",
            choices,
            current,
            on_change,
            subtitle="Applies XS/S/M/L/XL to the current mode: Slices, Hex, or Wall",
        )

    def _wallpaper_display_mode_row(self) -> Adw.ComboRow:
        def on_change(choice: str):
            set_nested(self._skwd_wall_config, ["components", "wallpaperSelector", "displayMode"], choice)
            set_nested(self._skwd_wall_config, ["components", "wallpaperSelector", "activeCustomPreset"], "")

        return self._combo_row_direct(
            "Display mode",
            ["slices", "hex", "wall"],
            self._wallpaper_display_mode(),
            on_change,
            subtitle="Selector layout used by the Quickshell wallpaper picker",
        )

    def _waybar_layout_options(self) -> list[str]:
        if not WAYBAR_LAYOUTS_DIR.exists():
            return []
        return sorted([p.name for p in WAYBAR_LAYOUTS_DIR.iterdir() if p.is_file()])

    def _waybar_style_options(self) -> list[str]:
        if not WAYBAR_STYLES_DIR.exists():
            return []
        return sorted([p.stem for p in WAYBAR_STYLES_DIR.glob("*.css") if p.is_file()])

    def _waybar_current_layout_name(self) -> str:
        raw = str(get_nested(self._config, ["components", "bar", "waybarConfig"], "~/.config/waybar/config"))
        fallback = Path(raw.replace("~", str(HOME)))
        if WAYBAR_CONFIG_LINK.exists():
            try:
                return WAYBAR_CONFIG_LINK.resolve().name
            except Exception:
                pass
        return fallback.name

    def _waybar_current_style_name(self) -> str:
        raw = str(get_nested(self._config, ["components", "bar", "waybarStyle"], "~/.config/waybar/style.css"))
        fallback = Path(raw.replace("~", str(HOME)))
        if WAYBAR_STYLE_LINK.exists():
            try:
                return WAYBAR_STYLE_LINK.resolve().stem
            except Exception:
                pass
        return fallback.stem

    def _waybar_layout_row(self) -> Adw.ComboRow:
        choices = self._waybar_layout_options()
        current = self._waybar_current_layout_name()
        custom_prefix = "Custom: "
        if current and current not in choices:
            choices = [custom_prefix + current] + choices

        def on_change(choice: str):
            if choice.startswith(custom_prefix) or choice == "No options found":
                return
            set_nested(self._config, ["components", "bar", "waybarConfig"], f"~/.config/waybar/configs/{choice}")
            set_nested(self._config, ["components", "bar", "waybarLayoutPreset"], choice)

        return self._combo_row_direct(
            "Layout preset",
            choices,
            custom_prefix + current if current and current not in choices else current,
            on_change,
            subtitle="Based on ~/.config/hypr/scripts/WaybarLayout.sh options",
        )

    def _waybar_style_row(self) -> Adw.ComboRow:
        choices = self._waybar_style_options()
        current = self._waybar_current_style_name()
        custom_prefix = "Custom: "
        if current and current not in choices:
            choices = [custom_prefix + current] + choices

        def on_change(choice: str):
            if choice.startswith(custom_prefix) or choice == "No options found":
                return
            set_nested(self._config, ["components", "bar", "waybarStyle"], f"~/.config/waybar/style/{choice}.css")
            set_nested(self._config, ["components", "bar", "waybarStylePreset"], choice)

        return self._combo_row_direct(
            "Style preset",
            choices,
            custom_prefix + current if current and current not in choices else current,
            on_change,
            subtitle="Based on ~/.config/hypr/scripts/WaybarStyles.sh options",
        )

    def _waybar_apply_row(self) -> Adw.ActionRow:
        row = Adw.ActionRow(
            title="Apply preset now",
            subtitle="Restart Waybar immediately with selected layout/style",
        )
        btn = Gtk.Button(label="Apply")
        btn.add_css_class("suggested-action")

        def _on_apply(_btn):
            prev_cfg = str(WAYBAR_CONFIG_LINK.resolve()) if WAYBAR_CONFIG_LINK.exists() else ""
            prev_sty = str(WAYBAR_STYLE_LINK.resolve()) if WAYBAR_STYLE_LINK.exists() else ""
            cfg_raw = str(get_nested(self._config, ["components", "bar", "waybarConfig"], "~/.config/waybar/config"))
            sty_raw = str(get_nested(self._config, ["components", "bar", "waybarStyle"], "~/.config/waybar/style.css"))
            cfg = str(Path(cfg_raw.replace("~", str(HOME))))
            sty = str(Path(sty_raw.replace("~", str(HOME))))
            sync_waybar_links(cfg, sty)
            ok = apply_waybar(True, cfg, sty, restart=True)
            if ok:
                self._toast("Waybar preset applied")
            else:
                if prev_cfg and prev_sty:
                    sync_waybar_links(prev_cfg, prev_sty)
                    apply_waybar(True, prev_cfg, prev_sty, restart=True)
                reason = _waybar_last_error_summary(style_path=sty)
                style_name = Path(sty).name
                msg = f"Waybar failed for {style_name}; restored previous working preset"
                if reason:
                    msg += f" ({reason})"
                self._toast(msg, timeout=4)

        btn.connect("clicked", _on_apply)
        row.add_suffix(btn)
        row.set_activatable_widget(btn)
        return row

    def _waybar_preview_row(self) -> Adw.ActionRow:
        row = Adw.ActionRow(
            title="Preview",
            subtitle="Placeholder only for now; add screenshots later",
        )

        frame = Gtk.Frame()
        frame.set_hexpand(True)
        frame.set_vexpand(False)
        frame.set_size_request(540, 180)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)

        icon = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
        icon.set_pixel_size(56)

        title = Gtk.Label(label="Waybar Preview Placeholder")
        title.add_css_class("title-4")

        subtitle = Gtk.Label(label="When ready, replace with per-preset screenshots")
        subtitle.add_css_class("dim-label")

        box.append(icon)
        box.append(title)
        box.append(subtitle)
        frame.set_child(box)
        row.set_child(frame)
        return row

    def _group(self, title: str, rows: list, description: str = "") -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=title)
        if description:
            group.set_description(description)
        for row in rows:
            group.add(row)
        return group

    def _info_row(self, title: str, subtitle: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title)
        row.set_subtitle(subtitle)
        row.set_activatable(False)
        return row

    def _action_row(self, title: str, subtitle: str, callback, button_label: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        btn = Gtk.Button(label=button_label)
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda *_: callback())
        row.add_suffix(btn)
        row.set_activatable_widget(btn)
        return row

    def _on_rescan_wallpapers(self):
        try:
            db_dir = HOME / ".local/share/quickshell/QML/OfflineStorage/Databases"
            if not db_dir.exists():
                self._toast("Database directory not found")
                return
            
            # Find the sqlite file that has the 'state' table
            found = False
            for p in db_dir.glob("*.sqlite"):
                # We check if it's our database by looking for the 'meta' and 'state' tables
                res = subprocess.run(["sqlite3", str(p), "SELECT name FROM sqlite_master WHERE type='table' AND name='state';"],
                                     capture_output=True, text=True)
                if "state" in res.stdout:
                    subprocess.run(["sqlite3", str(p), "DELETE FROM state WHERE key='last_rebuild';"])
                    found = True
                    # Do not break, there might be multiple or we might want to be sure
            
            if found:
                self._toast("Rescan triggered (Database reset)")
            else:
                self._toast("No active database found to reset")
        except Exception as e:
            self._toast(f"Rescan error: {e}")

    def _strip_ext(self, name: str) -> str:
        return re.sub(r'\.(jpg|jpeg|png|webp|gif|mp4|mkv|mov|webm|avi)$', '', name, flags=re.IGNORECASE)

    def _migrate_positions_to_extensions(self):
        wallpapers = self._get_wallpapers_from_db()
        # Create a map of stem -> full_filename
        stem_to_ext = {}
        for w in wallpapers:
            name = w["name"]
            stem = self._strip_ext(name)
            if stem not in stem_to_ext:
                stem_to_ext[stem] = name
        
        new_pos = {"default": self._positions.get("default", {})}
        
        # First, preserve all existing extensioned keys
        for key, val in self._positions.items():
            if key == "default": continue
            if "." in key: # Has extension
                new_pos[key] = val
        
        # Then, for each stem key, merge into extensioned key if it exists
        for key, val in self._positions.items():
            if key == "default" or "." in key: continue
            
            # This is a stem key. Find its extensioned counterpart.
            ext_key = stem_to_ext.get(key)
            if ext_key:
                # Merge: stem data overrides default but extensioned key might already have data.
                # If extensioned key exists, we prefer non-zero/non-default values from stem.
                if ext_key not in new_pos:
                    new_pos[ext_key] = val
                else:
                    # Merge logic: if stem has a value that is NOT default/zero, use it.
                    for k, v in val.items():
                        if v not in (0, False, None, 90, 25, 22): # Basic default check
                            new_pos[ext_key][k] = v
            # If no extensioned counterpart found on disk, we just discard the stem key
            # as per user request to clean up.
            
        self._positions = new_pos

    def _get_wallpapers_from_db(self) -> list[dict]:
        wallpapers = []
        try:
            db_dir = HOME / ".local/share/quickshell/QML/OfflineStorage/Databases"
            if not db_dir.exists():
                return []
            
            # Find the sqlite file that has the 'meta' table
            for p in db_dir.glob("*.sqlite"):
                conn = sqlite3.connect(p)
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT name, thumb, we_id FROM meta WHERE type IS NOT NULL")
                    rows = cursor.fetchall()
                    for row in rows:
                        wallpapers.append({"name": row[0], "thumb": row[1], "we_id": row[2]})
                    conn.close()
                    if wallpapers:
                        break # Found it
                except sqlite3.OperationalError:
                    conn.close()
                    continue
        except Exception as e:
            print(f"Error reading wallpapers from DB: {e}")
        
        # Sort by name, but prioritize those in positions.json if needed
        # For now just sort by name
        wallpapers.sort(key=lambda x: x["name"].lower())
        return wallpapers

    def _build_clock_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()

        # ── Active Wallpapers ──────────────────────────────────────────────────
        active_group = Adw.PreferencesGroup(
            title="Active Wallpapers",
            description="Quickly configure the clock for currently active wallpapers"
        )
        
        # Load wallpapers from DB for thumbnails
        wallpapers_raw = self._get_wallpapers_from_db()
        wallpapers_map = {w["name"]: w for w in wallpapers_raw}

        def auto_save_positions():
            save_json(POSITIONS_JSON_PATH, self._positions)
            self._saved_positions = deepcopy(self._positions)
            self._suppress_external_reload_until = time.time() + 1.2
            self._file_mtimes["positions.json"] = self._mtime(POSITIONS_JSON_PATH)

        def make_pos_switch(title, key, pos_data, name):
            row = Adw.SwitchRow(title=title)
            row.set_active(bool(pos_data.get(key, False)))
            def on_changed(r, _p):
                self._positions[name][key] = r.get_active()
                auto_save_positions()
            row.connect("notify::active", on_changed)
            return row

        def make_pos_spin(title, key, pos_data, name, min_v, max_v, step):
            row = Adw.ActionRow(title=title)
            val = float(pos_data.get(key, 0))
            adj = Gtk.Adjustment(value=val, lower=min_v, upper=max_v, step_increment=step)
            spin = Gtk.SpinButton(adjustment=adj, numeric=True)
            spin.set_valign(Gtk.Align.CENTER)
            def on_changed(s):
                self._positions[name][key] = int(s.get_value())
                auto_save_positions()
            spin.connect("value-changed", on_changed)
            row.add_suffix(spin)
            return row

        # Find active wallpaper files
        active_found = False
        if SKWD_WALL_CACHE_DIR.exists():
            for state_file in SKWD_WALL_CACHE_DIR.glob("last-wallpaper*.json"):
                try:
                    data = json.loads(state_file.read_text())
                    name = ""
                    path = data.get("path")
                    we_id = data.get("we_id")

                    if path:
                        name = Path(path).name
                    elif we_id:
                        # Try to resolve title from DB
                        db_found = False
                        for wall in wallpapers_raw:
                            if str(wall.get("we_id", "")).strip("'") == str(we_id):
                                name = wall["name"]
                                db_found = True
                                break
                        if not db_found:
                            name = str(we_id)
                    
                    if not name: continue
                    
                    monitor = ""
                    if state_file.stem.startswith("last-wallpaper-"):
                        monitor = state_file.stem[len("last-wallpaper-"):].replace("_", " ")

                    # Create expander for active wallpaper
                    wall_title = f"{name} ({monitor})" if monitor else name
                    expander = Adw.ExpanderRow(title=wall_title)
                    
                    if name not in self._positions:
                        self._positions[name] = deepcopy(self._positions.get("default", {}))

                    pos_data = self._positions[name]
                    
                    # Add controls
                    expander.add_row(make_pos_switch("Enabled", "enabled", pos_data, name))
                    expander.add_row(make_pos_switch("Center on Screen", "centerOnScreen", pos_data, name))
                    expander.add_row(make_pos_switch("Center X", "centerX", pos_data, name))
                    expander.add_row(make_pos_switch("Center Y", "centerY", pos_data, name))
                    expander.add_row(make_pos_spin("X Position", "x", pos_data, name, -5000, 5000, 10))
                    expander.add_row(make_pos_spin("Y Position", "y", pos_data, name, -5000, 5000, 10))
                    expander.add_row(make_pos_spin("Day Size", "daySize", pos_data, name, 1, 500, 1))
                    expander.add_row(make_pos_spin("Date Size", "dateSize", pos_data, name, 1, 500, 1))
                    expander.add_row(make_pos_spin("Time Size", "timeSize", pos_data, name, 1, 500, 1))
                    
                    # Thumbnail if available
                    wall_info = wallpapers_map.get(name)
                    if wall_info and wall_info.get("thumb"):
                        img = Gtk.Image.new_from_file(wall_info["thumb"])
                        img.set_pixel_size(64)
                        img.set_margin_start(12)
                        expander.add_prefix(img)

                    active_group.add(expander)
                    active_found = True
                except Exception as e:
                    print(f"Error loading active wallpaper state {state_file}: {e}")

        if active_found:
            page.add(active_group)

        # ── All Wallpapers ─────────────────────────────────────────────────────
        # Main group for individual wallpaper clock settings
        group = Adw.PreferencesGroup(
            title="Wallpaper Clock Positions",
            description="Configure the clock position for each wallpaper",
        )
        
        # Search entry to filter wallpapers
        search_row = Adw.ActionRow()
        search_entry = Gtk.SearchEntry(placeholder_text="Search wallpapers…", hexpand=True)
        search_row.set_child(search_entry)
        group.add(search_row)
        
        # Add keys from positions.json that aren't in DB
        for name in self._positions:
            if name != "default" and name not in wallpapers_map:
                wallpapers_map[name] = {"name": name, "thumb": None}
        
        sorted_names = sorted(wallpapers_map.keys(), key=lambda x: x.lower())
        
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")

        def build_wallpaper_row(name):
            wall = wallpapers_map[name]
            thumb_path = wall["thumb"]
            
            expander = Adw.ExpanderRow(title=name)
            
            prefix_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            if thumb_path and Path(thumb_path).exists():
                 img = Gtk.Image.new_from_file(thumb_path)
                 img.set_pixel_size(48)
                 prefix_box.append(img)
            else:
                 icon = Gtk.Image.new_from_icon_name("image-missing-symbolic")
                 icon.set_pixel_size(48)
                 prefix_box.append(icon)
            expander.add_prefix(prefix_box)

            if name not in self._positions:
                self._positions[name] = deepcopy(self._positions.get("default", {}))
            
            pos_data = self._positions[name]
            
            expander.add_row(make_pos_switch("Enabled", "enabled", pos_data, name))
            expander.add_row(make_pos_switch("Center on Screen", "centerOnScreen", pos_data, name))
            expander.add_row(make_pos_switch("Center X", "centerX", pos_data, name))
            expander.add_row(make_pos_switch("Center Y", "centerY", pos_data, name))
            expander.add_row(make_pos_spin("X Position", "x", pos_data, name, -5000, 5000, 10))
            expander.add_row(make_pos_spin("Y Position", "y", pos_data, name, -5000, 5000, 10))
            expander.add_row(make_pos_spin("Day Size", "daySize", pos_data, name, 1, 500, 1))
            expander.add_row(make_pos_spin("Date Size", "dateSize", pos_data, name, 1, 500, 1))
            expander.add_row(make_pos_spin("Time Size", "timeSize", pos_data, name, 1, 500, 1))
            return expander

        # Optimization: Only load first N wallpapers initially
        INITIAL_LIMIT = 25
        displayed_count = 0
        
        def populate_list(names_to_show):
            # Clear previous rows
            while child := listbox.get_first_child():
                listbox.remove(child)
            
            for name in names_to_show:
                listbox.append(build_wallpaper_row(name))

        # Initial population
        populate_list(sorted_names[:INITIAL_LIMIT])

        # Load more button
        load_more_row = Adw.ActionRow(title="Show all wallpapers…")
        load_more_row.set_activatable(True)
        load_more_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        
        def on_load_more_clicked(row):
            listbox.remove(row)
            # Rebuild full list (can be slow, but it's user-initiated)
            for name in sorted_names[INITIAL_LIMIT:]:
                listbox.append(build_wallpaper_row(name))
        
        load_more_row.connect("activated", on_load_more_clicked)
        if len(sorted_names) > INITIAL_LIMIT:
            listbox.append(load_more_row)

        group.add(listbox)
        page.add(group)
        
        # Search functionality - rebuilds list based on query
        def on_search_changed(entry):
            query = entry.get_text().lower()
            if not query:
                # Reset to initial limited list
                populate_list(sorted_names[:INITIAL_LIMIT])
                if len(sorted_names) > INITIAL_LIMIT:
                    listbox.append(load_more_row)
                return
            
            # Find matches in full list
            matches = [n for n in sorted_names if query in n.lower()]
            # Show up to 50 matches for performance
            populate_list(matches[:50])
            
            if len(matches) > 50:
                info_row = Adw.ActionRow(title=f"Showing 50 of {len(matches)} matches…")
                listbox.append(info_row)
        
        search_entry.connect("search-changed", on_search_changed)
        
        return page

    def _page(self, groups: list[Adw.PreferencesGroup]) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        for g in groups:
            page.add(g)
        return page

    def _terminal_row(self) -> Adw.ComboRow:
        choices = _detect_terminals()
        current = self._selected_terminal
        if current not in choices:
            choices = [current] + choices

        def on_change(choice: str):
            self._selected_terminal = choice

        return self._combo_row_direct(
            "Terminal",
            choices,
            current,
            on_change,
            subtitle="Writes to ~/.config/hypr/UserConfigs/01-UserDefaults.conf for Super+Enter",
        )

    def _shell_row(self) -> Adw.ComboRow:
        choices = _detect_shells()
        current = self._selected_shell
        if current not in choices:
            choices = [current] + choices

        def on_change(choice: str):
            self._selected_shell = choice

        return self._combo_row_direct(
            "Interpreter (Shell)",
            choices,
            current,
            on_change,
            subtitle="Default shell used by terminal (zsh recommended)",
        )

    def _monitor_rows(self) -> list:
        detected = _detect_monitors()
        # Get current order from config
        saved_list = get_nested(self._config, ["monitors_list"], [])
        if not saved_list:
            # Migration/init
            primary = str(get_nested(self._config, ["monitor"], "auto"))
            secondary = str(get_nested(self._config, ["secondary_monitor"], "auto"))
            saved_list = [primary]
            if secondary != "auto":
                saved_list.append(secondary)
        
        # Determine how many rows to show: at least one, or up to N detected monitors
        num_rows = max(1, len(detected))
        rows = []
        
        for i in range(num_rows):
            label = _get_monitor_label(i)
            current = saved_list[i] if i < len(saved_list) else "auto"
            if current not in detected and current != "auto":
                if i < len(detected):
                    current = detected[i]
                else:
                    current = "auto"

            def make_on_change(idx):
                def on_change(choice: str):
                    mlist = get_nested(self._config, ["monitors_list"], [])
                    if not mlist: # init if empty
                         mlist = [str(get_nested(self._config, ["monitor"], "auto")), 
                                  str(get_nested(self._config, ["secondary_monitor"], "auto"))]
                    
                    while len(mlist) <= idx:
                        mlist.append("auto")
                    mlist[idx] = choice
                    set_nested(self._config, ["monitors_list"], mlist)
                    
                    # Backward compatibility for 'monitor' and 'secondary_monitor' keys
                    if idx == 0:
                        set_nested(self._config, ["monitor"], choice)
                    elif idx == 1:
                        set_nested(self._config, ["secondary_monitor"], choice)
                    
                    self._mark_unsaved()
                return on_change

            row = self._combo_row_direct(
                label,
                detected,
                current,
                make_on_change(i),
                subtitle=f"Display assignment for {label}"
            )
            
            # Disable secondary+ rows if only one monitor is available
            if i > 0 and len(detected) < 2:
                row.set_sensitive(False)
            
            rows.append(row)
        
        if get_nested(self._config, ["components", "bar", "secondaryBarEnabled"], None) is None:
            set_nested(self._config, ["components", "bar", "secondaryBarEnabled"], True)
        rows.append(self._switch_row(
            "Secondary Monitor Bar",
            ["components", "bar", "secondaryBarEnabled"],
            subtitle="Show Waybar on secondary monitor (disable if only one screen is connected)",
        ))

        nwg_row = Adw.ActionRow(
            title="Manage Displays (nwg-displays)",
            subtitle="Open advanced monitor arrangement tool",
        )
        nwg_btn = Gtk.Button(label="Open")
        nwg_btn.add_css_class("suggested-action")
        nwg_btn.connect("clicked", lambda *_: subprocess.Popen(["nwg-displays"]))
        nwg_row.add_suffix(nwg_btn)
        nwg_row.set_activatable_widget(nwg_btn)
        rows.append(nwg_row)

        return rows

    def _gpu_vendor_row(self) -> Adw.ComboRow:
        choices = ["auto", "nvidia", "amd", "intel", "other"]

        def on_change(choice: str):
            self._selected_gpu_vendor = choice

        return self._combo_row_direct(
            "GPU vendor",
            choices,
            self._selected_gpu_vendor if self._selected_gpu_vendor in choices else "auto",
            on_change,
            subtitle="Writes environment presets to ~/.config/hypr/UserConfigs/ENVariables.conf",
        )

    def _color_mode_row(self) -> Adw.ComboRow:
        choices = ["dark", "light"]

        def on_change(choice: str):
            self._selected_color_mode = choice
            set_nested(self._config, ["appearance", "colorMode"], choice)
            self._apply_color_mode_style()

        return self._combo_row_direct(
            "System colors",
            choices,
            self._selected_color_mode if self._selected_color_mode in choices else _read_theme_mode(),
            on_change,
            subtitle="Applies the global light/dark system palette",
        )

    def _startup_label(self, cmd: str) -> str:
        first = cmd.split()[0] if cmd.split() else cmd
        return Path(first).name or cmd

    def _startup_switch_row(self, app: dict) -> Adw.SwitchRow:
        title = self._startup_label(app.get("cmd", ""))
        row = Adw.SwitchRow(title=title)
        row.set_active(bool(app.get("enabled", True)))
        subtitle = app.get("cmd", "")
        if app.get("system"):
            subtitle = f"System entry: {subtitle}"
        row.set_subtitle(subtitle)

        def on_toggle(r, _p, item=app):
            item["enabled"] = r.get_active()
            self._mark_unsaved()

        row.connect("notify::active", on_toggle)
        return row

    def _workspace_choices(self, current: str = "") -> list[str]:
        base = [str(i) for i in range(1, 11)]
        if current and current not in base:
            return [current] + base
        return base

    def _workspace_rule_row(self, rule: dict) -> Adw.ComboRow:
        current = str(rule.get("workspace", "1") or "1")

        def on_change(choice: str, item=rule):
            item["workspace"] = choice

        return self._combo_row_direct(
            rule.get("selector", "Window rule"),
            self._workspace_choices(current),
            current,
            on_change,
            subtitle=f"match:{'tag' if 'match:tag' in rule.get('line', '') else 'class'} {rule.get('selector', '')}",
        )

    # ── Pages ─────────────────────────────────────────────────────────────────

    def _build_general_page(self) -> Adw.PreferencesPage:
        system_rows = [
            self._info_row("Compositor", f"Read-only: {self._selected_compositor}"),
            self._terminal_row(),
            self._shell_row(),
            self._gpu_vendor_row(),
        ]
        system_rows.extend(self._monitor_rows())
        
        return self._page([
            self._group("System", system_rows),
            self._group("Paths", [
                self._entry_row("Scripts",   ["paths", "scripts"]),
                self._entry_row("Cache",     ["paths", "cache"]),
                self._entry_row("Wallpaper", ["paths", "wallpaper"]),
                self._entry_row("Steam",     ["paths", "steam"]),
            ]),
            self._group("Ollama", [
                self._entry_row("URL",   ["ollama", "url"]),
                self._entry_row("Model", ["ollama", "model"]),
            ]),
            self._group("Matugen", [
                self._combo_row("Scheme type", ["matugen", "schemeType"], [
                    "scheme-fidelity", "scheme-tonal-spot", "scheme-content",
                    "scheme-expressive", "scheme-monochrome", "scheme-neutral",
                    "scheme-rainbow", "scheme-fruit-salad",
                ]),
                self._entry_row("KDE color scheme name", ["matugen", "kdeColorScheme"]),
            ]),
            self._group("Performance", [
                self._switch_row("Optimization mode", ["optimization", "enabled"],
                                 subtitle="Maximum optimization: disables most shell components except wallpapers"),
                self._switch_row("Disable borders", ["optimization", "toggles", "disableBorders"],
                                 subtitle="Sets border size to 0"),
                self._switch_row("Disable transparency", ["optimization", "toggles", "disableTransparency"],
                                 subtitle="Forces inactive opacity to 1.0"),
                self._switch_row("Disable animations", ["optimization", "toggles", "disableAnimations"],
                                 subtitle="Turns off Hyprland animations"),
                self._switch_row("Disable Quickshell animations", ["optimization", "toggles", "disableQuickshellAnimations"],
                                 subtitle="Disables Quickshell UI animations and reduces heavy visual effects"),
                self._switch_row("Disable blur", ["optimization", "toggles", "disableBlur"],
                                 subtitle="Disables decoration blur"),
                self._switch_row("Disable shadows", ["optimization", "toggles", "disableShadows"],
                                 subtitle="Disables window shadows"),
                self._switch_row("Disable rounding", ["optimization", "toggles", "disableRounding"],
                                 subtitle="Sets window rounding to 0"),
                self._switch_row("Disable gaps", ["optimization", "toggles", "disableGaps"],
                                 subtitle="Sets gaps_in and gaps_out to 0"),
                self._switch_row("Disable dim inactive", ["optimization", "toggles", "disableDimInactive"],
                                 subtitle="Disables inactive window dimming"),
            ]),
        ])

    def _build_screen_page(self) -> Adw.PreferencesPage:
        return self._page([
            self._group("Bar", [
                self._switch_row("Enabled", ["components", "bar", "enabled"]),
                self._combo_row("Backend", ["components", "bar", "backend"], ["waybar", "quickshell"]),
                self._entry_row("Waybar config path", ["components", "bar", "waybarConfig"]),
                self._entry_row("Waybar style path",  ["components", "bar", "waybarStyle"]),
            ]),
            self._group("Waybar presets", [
                self._waybar_layout_row(),
                self._waybar_style_row(),
                self._waybar_apply_row(),
            ], description="Switch among existing Waybar layouts/styles without Rofi"),
            self._group("Waybar preview", [
                self._waybar_preview_row(),
            ]),
            self._group("Widgets", [
                self._switch_row("Volume",    ["components", "bar", "volume"]),
                self._switch_row("Calendar",  ["components", "bar", "calendar"]),
                self._switch_row("Bluetooth", ["components", "bar", "bluetooth"]),
            ]),
            self._group("Weather", [
                self._switch_row("Enabled", ["components", "bar", "weather", "enabled"]),
                self._entry_row("City",     ["components", "bar", "weather", "city"]),
            ]),
            self._group("Wifi", [
                self._switch_row("Enabled",  ["components", "bar", "wifi", "enabled"]),
                self._entry_row("Interface", ["components", "bar", "wifi", "interface"]),
            ]),
            self._group("Music / MPRIS", [
                self._switch_row("Enabled",           ["components", "bar", "music", "enabled"]),
                self._entry_row("Preferred player",    ["components", "bar", "music", "preferredPlayer"]),
                self._combo_row("Visualizer",          ["components", "bar", "music", "visualizer"],
                                ["wave", "bars", "off"]),
                self._switch_row("Visualizer top",     ["components", "bar", "music", "visualizerTop"]),
                self._switch_row("Visualizer bottom",  ["components", "bar", "music", "visualizerBottom"]),
            ]),
            self._group("Wallpapers", [
                self._combo_row("Backend", ["components", "wallpaperSelector", "backend"], ["quickshell", "rofi"]),
                self._switch_row("Mute wallpaper audio", ["wallpaperMute"], config_src=self._skwd_wall_config),
                self._wallpaper_display_mode_row(),
                self._wallpaper_size_preset_row(),
                self._color_mode_row(),
                self._switch_row("Auto change",
                                 ["components", "wallpaperSelector", "autoChangeEnabled"],
                                 config_src=self._skwd_wall_config),
                self._combo_row("Auto change mode",
                                ["components", "wallpaperSelector", "autoChangeMode"],
                                ["random", "next"],
                                config_src=self._skwd_wall_config),
                self._spin_row("Auto change interval (minutes)",
                               ["components", "wallpaperSelector", "autoChangeIntervalMinutes"],
                               min_val=1, max_val=1440, step=5,
                               config_src=self._skwd_wall_config),
                self._switch_row("Same wallpaper all monitors",
                                 ["sameWallpaperAllMonitors"],
                                 config_src=self._skwd_wall_config),
                self._spin_row("Columns",
                               ["components", "wallpaperSelector", "wallhavenColumns"],
                               min_val=1, max_val=20,
                               config_src=self._skwd_wall_config),
                self._spin_row("Rows",
                               ["components", "wallpaperSelector", "wallhavenRows"],
                               min_val=1, max_val=20,
                               config_src=self._skwd_wall_config),
                self._entry_row("Steam Workshop",  ["paths", "steamWorkshop"], config_src=self._skwd_wall_config),
                self._entry_row("Steam WE assets", ["paths", "steamWeAssets"], config_src=self._skwd_wall_config),
                self._entry_row("Clock positions file", ["paths", "clockPositions"], config_src=self._skwd_wall_config),
                self._action_row("Rescan wallpapers", "Scan for new images or videos", self._on_rescan_wallpapers, "Rescan"),
            ], description="Display-related settings: bar and wallpapers"),
        ])

    def _build_components_page(self) -> Adw.PreferencesPage:
        return self._page([
            self._group("App launcher", [
                self._switch_row("Enabled", ["components", "appLauncher", "enabled"]),
                self._combo_row("Backend", ["components", "appLauncher", "backend"], ["quickshell", "rofi", "fuzzel"]),
            ]),
            self._group("Window switcher", [
                self._switch_row("Enabled", ["components", "windowSwitcher"]),
            ]),
            self._group("Notifications", [
                self._switch_row("Enabled", ["components", "notifications"]),
            ]),
            self._group("Lockscreen", [
                self._switch_row("Enabled", ["components", "lockscreen"]),
            ]),
            self._group("Smart home", [
                self._switch_row("Enabled", ["components", "smartHome"]),
            ]),
            self._group("Power menu", [
                self._switch_row("Enabled", ["components", "powerMenu", "enabled"]),
            ]),
            self._group("Wallpaper selector", [
                self._switch_row("Enabled",        ["components", "wallpaperSelector", "enabled"]),
                self._combo_row("Backend",         ["components", "wallpaperSelector", "backend"], ["quickshell", "rofi"]),
                self._switch_row("Show color dots", ["components", "wallpaperSelector", "showColorDots"]),
            ]),
        ])

    def _build_power_page(self) -> Adw.PreferencesPage:
        return self._page([
            self._group("Device", [
                self._combo_row("Device type", ["power", "deviceType"],
                                ["auto", "laptop", "desktop"]),
            ]),
            self._group("Profile", [
                self._combo_row("Power profile", ["power", "profile"],
                                ["power-saver", "balanced", "performance"]),
            ]),
        ])

    def _build_hypridle_page(self) -> Adw.PreferencesPage:
        return self._page([
            self._group("Daemon", [
                self._switch_row("Enabled", ["hypridle", "enabled"],
                                 subtitle="Start or stop hypridle when saving settings"),
                self._switch_row("Ignore DBus inhibit", ["hypridle", "ignoreDbusInhibit"],
                                 subtitle="Maps to ignore_dbus_inhibit in hypridle.conf"),
            ]),
            self._group("Timeouts", [
                self._spin_row("Warn timeout (minutes)",
                               ["hypridle", "warnMinutes"],
                               min_val=1, max_val=240, step=1,
                               subtitle="Idle warning notification timeout"),
                self._spin_row("Lock timeout (minutes)",
                               ["hypridle", "lockMinutes"],
                               min_val=1, max_val=480, step=1,
                               subtitle="Session lock timeout"),
            ]),
            self._group("Source", [
                self._info_row("Config file", str(HYPRIDLE_CONF_PATH)),
            ], description="Save applies changes into ~/.config/hypr/hypridle.conf and restarts hypridle"),
        ])

    def _build_integrations_page(self) -> Adw.PreferencesPage:
        return self._page([
            self._group("Theme integrations", [
                self._entry_row("Kitty",         ["integrations", "kitty"]),
                self._entry_row("KDE colors",    ["integrations", "kde"]),
                self._entry_row("VSCode",        ["integrations", "vscode"]),
                self._entry_row("Vesktop",       ["integrations", "vesktop"]),
                self._entry_row("Zen browser",   ["integrations", "zen"]),
                self._entry_row("Spicetify",     ["integrations", "spicetify"]),
                self._entry_row("Spicetify CSS", ["integrations", "spicetifyCss"]),
                self._entry_row("Yazi",          ["integrations", "yazi"]),
                self._entry_row("Qt6ct",         ["integrations", "qt6ct"]),
            ]),
        ])

    def _build_apps_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="App customization",
            description="Override display name, icon, and appearance per app",
        )

        for app_key, app_data in self._apps.items():
            if app_key.startswith("_"):
                continue
            if not isinstance(app_data, dict):
                continue

            expander = Adw.ExpanderRow(
                title=app_data.get("displayName") or app_key,
                subtitle=", ".join(app_data.get("tags") or []) or app_key,
            )

            def _make_entry(a_key: str, field: str, label: str, initial: str) -> Adw.EntryRow:
                r = Adw.EntryRow(title=label)
                r.set_text(str(initial or ""))
                def on_ch(row, k=a_key, f=field):
                    if k not in self._apps or not isinstance(self._apps[k], dict):
                        self._apps[k] = {}
                    text = row.get_text()
                    if f == "tags":
                        self._apps[k][f] = [t.strip() for t in text.split(",") if t.strip()]
                    else:
                        self._apps[k][f] = text
                    self._mark_unsaved()
                r.connect("changed", on_ch)
                return r

            def _make_switch(a_key: str, field: str, label: str, initial: bool) -> Adw.SwitchRow:
                r = Adw.SwitchRow(title=label)
                r.set_active(bool(initial))
                def on_tg(row, _p, k=a_key, f=field):
                    if k not in self._apps or not isinstance(self._apps[k], dict):
                        self._apps[k] = {}
                    self._apps[k][f] = row.get_active()
                    self._mark_unsaved()
                r.connect("notify::active", on_tg)
                return r

            expander.add_row(_make_entry(app_key, "displayName", "Display name",
                                         app_data.get("displayName", "")))
            expander.add_row(_make_entry(app_key, "icon", "Icon glyph",
                                         app_data.get("icon", "")))
            expander.add_row(_make_entry(app_key, "tags", "Tags (comma separated)",
                                         ", ".join(app_data.get("tags") or [])))
            expander.add_row(_make_switch(app_key, "hidden", "Hidden",
                                          app_data.get("hidden", False)))
            expander.add_row(_make_entry(app_key, "background", "Background path",
                                         app_data.get("background", "")))
            group.add(expander)

        page.add(group)
        return page

    def _build_intervals_page(self) -> Adw.PreferencesPage:
        return self._page([
            self._group("Poll intervals (milliseconds)", [
                self._spin_row("Weather",             ["intervals", "weatherPollMs"],
                               min_val=1000, max_val=3_600_000, step=1000),
                self._spin_row("Wifi",                ["intervals", "wifiPollMs"],
                               min_val=1000, max_val=60_000, step=1000),
                self._spin_row("Smart home",          ["intervals", "smartHomePollMs"],
                               min_val=1000, max_val=60_000, step=1000),
                self._spin_row("Ollama status",       ["intervals", "ollamaStatusPollMs"],
                               min_val=1000, max_val=60_000, step=1000),
                self._spin_row("Notification expire", ["intervals", "notificationExpireMs"],
                               min_val=500,  max_val=30_000, step=500),
            ]),
        ])

    def _build_startup_apps_page(self) -> Adw.PreferencesPage:
        groups = []

        controls = [
            self._info_row("Source", str(STARTUP_APPS_PATH)),
        ]
        toggle = Adw.SwitchRow(title="Show system entries")
        toggle.set_active(self._startup_show_system)

        def on_show_system(r, _p):
            self._startup_show_system = r.get_active()
            self._refresh_pages()

        toggle.connect("notify::active", on_show_system)
        controls.insert(0, toggle)
        groups.append(self._group("Visibility", controls))

        user_rows = []
        system_rows = []
        for app in self._startup_apps:
            row = self._startup_switch_row(app)
            if app.get("system"):
                system_rows.append(row)
            else:
                user_rows.append(row)

        if user_rows:
            groups.append(self._group("Startup apps", user_rows, description="Toggle optional applications launched at session start"))
        if self._startup_show_system and system_rows:
            groups.append(self._group("System entries", system_rows, description="Hidden helpers required for the desktop session"))
        if not user_rows and not system_rows:
            groups.append(self._group("Startup apps", [self._info_row("No entries", "No exec-once commands were detected")]))

        return self._page(groups)

    def _build_window_rules_page(self) -> Adw.PreferencesPage:
        rows = [self._info_row("Source", str(WINDOW_RULES_PATH))]
        if not self._workspace_rules:
            rows.append(self._info_row("No rules", "No workspace rules were found in WindowRules.conf"))
        else:
            for rule in self._workspace_rules:
                rows.append(self._workspace_rule_row(rule))
        return self._page([
            self._group("Workspace assignment", rows, description="Only the target workspace is editable; matching rules stay intact"),
        ])

    def _build_keybinds_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()

        # Filter controls
        filter_group = Adw.PreferencesGroup()
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_box.set_margin_top(6)
        filter_box.set_margin_bottom(6)

        self._kb_search = Gtk.SearchEntry(placeholder_text="Filter keybinds…", hexpand=True)
        filter_box.append(self._kb_search)

        self._kb_all_btn = Gtk.ToggleButton(label="All",  active=True)
        self._kb_on_btn  = Gtk.ToggleButton(label="On",   group=self._kb_all_btn)
        self._kb_off_btn = Gtk.ToggleButton(label="Off",  group=self._kb_all_btn)
        for btn in (self._kb_all_btn, self._kb_on_btn, self._kb_off_btn):
            btn.add_css_class("flat")
            filter_box.append(btn)

        refresh_btn = Gtk.Button(label="↺ Reload")
        refresh_btn.add_css_class("flat")
        filter_box.append(refresh_btn)

        filter_row = Adw.ActionRow()
        filter_row.set_child(filter_box)
        filter_group.add(filter_row)
        page.add(filter_group)

        self._kb_group = Adw.PreferencesGroup(title="Binds")
        page.add(self._kb_group)

        self._kb_state = "all"
        self._kb_query = ""
        self._rebuild_keybind_rows()

        self._kb_search.connect("search-changed", lambda s: self._kb_filter_update(query=s.get_text()))
        self._kb_all_btn.connect("toggled",  lambda b: b.get_active() and self._kb_filter_update(state="all"))
        self._kb_on_btn.connect("toggled",   lambda b: b.get_active() and self._kb_filter_update(state="on"))
        self._kb_off_btn.connect("toggled",  lambda b: b.get_active() and self._kb_filter_update(state="off"))
        refresh_btn.connect("clicked",       lambda _: self._reload_keybinds())

        return page

    def _kb_filter_update(self, *, query: str | None = None, state: str | None = None):
        if query is not None:
            self._kb_query = query.lower()
        if state is not None:
            self._kb_state = state
        self._rebuild_keybind_rows()

    def _reload_keybinds(self):
        self._load_keybinds()
        self._rebuild_keybind_rows()

    def _rebuild_keybind_rows(self):
        # Clear rows (skip non-ActionRow children like the header)
        to_remove = []
        child = self._kb_group.get_first_child()
        while child:
            if isinstance(child, Adw.ActionRow):
                to_remove.append(child)
            child = child.get_next_sibling()
        for c in to_remove:
            self._kb_group.remove(c)

        q = self._kb_query
        state = self._kb_state
        shown = 0

        for bind in self._keybinds_all:
            if state == "on"  and not bind["enabled"]: continue
            if state == "off" and     bind["enabled"]: continue
            row_text = f"{bind['source']} {bind['mods']} {bind['key']} {bind['dispatcher']} {bind['arg']} {bind['description']}".lower()
            if q and q not in row_text:
                continue

            mods_str = f"{bind['mods']} + " if bind["mods"].strip() else ""
            subtitle  = f"{mods_str}{bind['key']}  →  {bind['dispatcher']}"
            if bind["arg"]:
                subtitle += f",  {bind['arg']}"

            row = Adw.ActionRow(
                title=GLib.markup_escape_text(bind["description"] or bind["dispatcher"]),
                subtitle=GLib.markup_escape_text(subtitle),
            )

            source_lbl = Gtk.Label(
                label=bind["source"],
                css_classes=["caption", "dim-label"],
                valign=Gtk.Align.CENTER,
            )
            sw = Gtk.Switch(valign=Gtk.Align.CENTER, active=bind["enabled"])

            def on_sw(s, _p, uid=bind["uid"]):
                for b in self._keybinds_all:
                    if b["uid"] == uid:
                        b["enabled"] = s.get_active()
                        break
                self._mark_unsaved()

            sw.connect("notify::active", on_sw)
            row.add_suffix(source_lbl)
            row.add_suffix(sw)
            self._kb_group.add(row)
            shown += 1

        self._kb_group.set_title(f"Binds ({shown})")


# ── Application ───────────────────────────────────────────────────────────────

class ConfigApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.sdrxdots.ConfigPanel",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._win = None
        self.connect("activate", self._on_activate)

    def _on_activate(self, app):
        if self._win is None:
            self._win = ConfigWindow(application=app)
        self._win.present()


if __name__ == "__main__":
    import sys
    app = ConfigApp()
    sys.exit(app.run(None))
