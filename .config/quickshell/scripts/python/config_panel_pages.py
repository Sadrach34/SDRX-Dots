from gi.repository import Gtk, Adw, GLib, Pango
import json
import sqlite3
from pathlib import Path
from copy import deepcopy
from config_panel_constants import *
from config_panel_helpers import (
    _detect_terminals, _read_theme_mode,
    apply_waybar, sync_waybar_links, _waybar_last_error_summary,
    get_nested, set_nested,
)


class PageBuilderMixin:

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
            if all(selector.get(k) == v for k, v in fields.items()):
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

    def _strip_ext(self, name: str) -> str:
        return re.sub(r'\.(jpg|jpeg|png|webp|gif|mp4|mkv|mov|webm|avi)$', '', name, flags=re.IGNORECASE)

    def _action_row(self, title: str, subtitle: str, callback, button_label: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        btn = Gtk.Button(label=button_label)
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda *_: callback())
        row.add_suffix(btn)
        row.set_activatable_widget(btn)
        return row

    def _page(self, groups: list[Adw.PreferencesGroup]) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        for g in groups:
            page.add(g)
        return page

    def _get_wallpapers_from_db(self) -> list[dict]:
        wallpapers = []
        try:
            db_dir = HOME / ".local/share/quickshell/QML/OfflineStorage/Databases"
            if not db_dir.exists():
                return []
            
            for p in db_dir.glob("*.sqlite"):
                conn = sqlite3.connect(p)
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT name, thumb FROM meta WHERE type IS NOT NULL")
                    rows = cursor.fetchall()
                    for row in rows:
                        wallpapers.append({"name": row[0], "thumb": row[1]})
                    conn.close()
                    if wallpapers:
                        break
                except sqlite3.OperationalError:
                    conn.close()
                    continue
        except Exception as e:
            print(f"Error reading wallpapers from DB: {e}")
        
        wallpapers.sort(key=lambda x: x["name"].lower())
        return wallpapers

    def _build_clock_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="Wallpaper Clock Positions",
            description="Configure the clock position for each wallpaper",
        )
        
        search_row = Adw.ActionRow()
        search_entry = Gtk.SearchEntry(placeholder_text="Search wallpapers…", hexpand=True)
        search_row.set_child(search_entry)
        group.add(search_row)
        
        wallpapers_raw = self._get_wallpapers_from_db()
        # Use full filenames as keys
        wallpapers_map = {w["name"]: w for w in wallpapers_raw}
        
        # Add keys from positions.json that aren't in DB
        for name in self._positions:
            if name != "default" and name not in wallpapers_map:
                wallpapers_map[name] = {"name": name, "thumb": None}
        
        sorted_names = sorted(wallpapers_map.keys(), key=lambda x: x.lower())
        
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")

        def auto_save_positions():
            save_json(POSITIONS_JSON_PATH, self._positions)
            self._saved_positions = deepcopy(self._positions)
            # Prevent the file watcher from triggering a full UI reload
            import time
            self._suppress_external_reload_until = time.time() + 1.2
        
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

        for name in sorted_names:
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
            
            listbox.append(expander)

        group.add(listbox)
        page.add(group)
        
        def on_search_changed(entry):
            text = entry.get_text().lower()
            child = listbox.get_first_child()
            while child:
                if isinstance(child, Adw.ExpanderRow):
                    child.set_visible(text in child.get_title().lower())
                child = child.get_next_sibling()
        
        search_entry.connect("search-changed", on_search_changed)
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
        return self._page([
            self._group("System", [
                self._info_row("Compositor", f"Read-only: {self._selected_compositor}"),
                self._terminal_row(),
                self._gpu_vendor_row(),
                self._entry_row("Monitor",    ["monitor"]),
            ]),
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
            self._group("Components", [
                self._switch_row("App launcher",    ["components", "appLauncher", "enabled"]),
                self._switch_row("Window switcher", ["components", "windowSwitcher"]),
                self._switch_row("Notifications",   ["components", "notifications"]),
                self._switch_row("Lockscreen",      ["components", "lockscreen"]),
                self._switch_row("Smart home",      ["components", "smartHome"]),
            ]),
            self._group("Power menu", [
                self._switch_row("Enabled", ["components", "powerMenu", "enabled"]),
            ]),
            self._group("Wallpaper selector", [
                self._switch_row("Enabled",        ["components", "wallpaperSelector", "enabled"]),
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

    def _build_rofi_quickshell_page(self) -> Adw.PreferencesPage:
        return self._page([
            self._group("App Launcher", [
                self._switch_row("Enabled",        ["components", "appLauncher", "enabled"]),
                self._combo_row("Backend",         ["components", "appLauncher", "backend"], ["quickshell", "rofi", "fuzzel"]),
            ]),
            self._group("Wallpaper Selector", [
                self._switch_row("Enabled",        ["components", "wallpaperSelector", "enabled"]),
                self._combo_row("Backend",         ["components", "wallpaperSelector", "backend"], ["quickshell", "rofi"]),
                self._switch_row("Show color dots", ["components", "wallpaperSelector", "showColorDots"]),
            ]),
            self._group("Waybar Modules", [
                self._switch_row("Top Panel",      ["components", "bar", "topPanel"]),
                self._switch_row("Dashboard",      ["components", "bar", "dashboard"]),
            ]),
            self._group("Auto-start", [], "Quickshell se inicia automáticamente solo si al menos uno de sus componentes está habilitado."),
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
