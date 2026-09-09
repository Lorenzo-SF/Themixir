#!/usr/bin/env python3
"""Themixir theme generator (schema v2).

Reads Themixir.json (schema v2): 10 base palettes × 5 variants
(solarized, light, normal, dark, solarized_dark). Produces 50 theme
JSON files under themes/ and rewrites the `contributes.themes` array in
package.json. Uses pure Python for color math (harmonies, darken,
lighten) and shells out to alaja only for WCAG ratio validation.

Run: python3 generate_themes.py
"""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).parent
ALAJA = "/home/lorenzo/bin/alaja"

VARIANTS = ["solarized", "light", "normal", "dark", "solarized_dark"]
# Variant → uiTheme (light vs dark base)
UI_THEME = {"solarized": "vs", "light": "vs", "normal": "vs-dark",
            "dark": "vs-dark", "solarized_dark": "vs-dark"}
# Variant → file suffix (empty for "normal")
FILE_SUFFIX = {"solarized": "_solarized", "light": "_light",
               "normal": "", "dark": "_dark", "solarized_dark": "_solarized_dark"}
# Variant → display suffix (empty for "normal")
DISPLAY_SUFFIX = {"solarized": " Solarized", "light": " Light",
                  "normal": "", "dark": " Dark",
                  "solarized_dark": " Solarized Dark"}


# ----------------------------------------------------------------------
# Color math
# ----------------------------------------------------------------------

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, int(round(r)))),
        max(0, min(255, int(round(g)))),
        max(0, min(255, int(round(b)))),
    )


def _rgb_to_hsl(r, g, b) -> tuple[float, float, float]:
    r, g, b = r / 255, g / 255, b / 255
    mx, mn = max(r, g, b), min(r, g, b)
    h = s = 0.0
    l = (mx + mn) / 2
    if mx != mn:
        d = mx - mn
        s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r:
            h = ((g - b) / d + (6 if g < b else 0)) / 6
        elif mx == g:
            h = ((b - r) / d + 2) / 6
        else:
            h = ((r - g) / d + 4) / 6
    return h * 360, s, l


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    h = (h % 360) / 360

    def _q(p: float, q: float, t: float) -> float:
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    if s == 0:
        r = g = b = l
    else:
        q = l * (1 + s) if l < 0.5 else l + s - l * s
        p = 2 * l - q
        r = _q(p, q, h + 1 / 3)
        g = _q(p, q, h)
        b = _q(p, q, h - 1 / 3)
    return r * 255, g * 255, b * 255


def darken(hex_color: str, amount: float = 0.2) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(r * (1 - amount), g * (1 - amount), b * (1 - amount))


def lighten(hex_color: str, amount: float = 0.2) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(
        r + (255 - r) * amount,
        g + (255 - g) * amount,
        b + (255 - b) * amount,
    )


def _mix(hex_color: str, with_bg: str, alpha: float) -> str:
    """Mix hex_color with with_bg by alpha (0 = hex_color, 1 = with_bg)."""
    r1, g1, b1 = _hex_to_rgb(hex_color)
    r2, g2, b2 = _hex_to_rgb(with_bg)
    return _rgb_to_hex(
        r1 * (1 - alpha) + r2 * alpha,
        g1 * (1 - alpha) + g2 * alpha,
        b1 * (1 - alpha) + b2 * alpha,
    )


def _is_light_bg(bg_hex: str) -> bool:
    r, g, b = _hex_to_rgb(bg_hex)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return lum > 0.5


def _rotate_hue(hex_color: str, degrees: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    h, s, l = _rgb_to_hsl(r, g, b)
    h = (h + degrees) % 360
    nr, ng, nb = _hsl_to_rgb(h, s, l)
    return _rgb_to_hex(nr, ng, nb)


def analogous(hex_color: str) -> list[str]:
    return [_rotate_hue(hex_color, -30), hex_color, _rotate_hue(hex_color, 30)]


def triad(hex_color: str) -> list[str]:
    return [hex_color, _rotate_hue(hex_color, 120), _rotate_hue(hex_color, 240)]


def complementary(hex_color: str) -> list[str]:
    return [hex_color, _rotate_hue(hex_color, 180)]


def split_complementary(hex_color: str) -> list[str]:
    return [hex_color, _rotate_hue(hex_color, 150), _rotate_hue(hex_color, 210)]


# ----------------------------------------------------------------------
# WCAG validation (pure Python — much faster than shelling out per check)
# ----------------------------------------------------------------------

def _srgb_to_linear(c: float) -> float:
    """Convert sRGB component (0-1) to linear-light (0-1)."""
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    """Compute WCAG relative luminance for a hex color (0-1)."""
    h = hex_color.lstrip("#")
    r = _srgb_to_linear(int(h[0:2], 16) / 255)
    g = _srgb_to_linear(int(h[2:4], 16) / 255)
    b = _srgb_to_linear(int(h[4:6], 16) / 255)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag_ratio(fg: str, bg: str) -> float:
    """Compute WCAG ratio between fg and bg (both hex).

    Verified against alaja: matches to within rounding.
    """
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _ensure_contrast(fg: str, bg: str, min_ratio: float = 4.5) -> str:
    """If fg vs bg is below min_ratio, darken/lighten fg until it passes."""
    if wcag_ratio(fg, bg) >= min_ratio:
        return fg
    # Try alternating darken/lighten
    for step in range(1, 11):
        candidate = darken(fg, step * 0.1)
        if wcag_ratio(candidate, bg) >= min_ratio:
            return candidate
    for step in range(1, 11):
        candidate = lighten(fg, step * 0.1)
        if wcag_ratio(candidate, bg) >= min_ratio:
            return candidate
    return fg  # give up


# ----------------------------------------------------------------------
# Theme builder
# ----------------------------------------------------------------------

def _a(hex_color: str, alpha_hex: str) -> str:
    """Append alpha channel (2 hex digits) to a 6-digit hex color."""
    return hex_color.lstrip("#") + alpha_hex.upper()


def build_theme(color_name: str, variant: str, palette: dict) -> dict:
    selection = palette["selection"]
    accent = palette["accent"]
    bg = palette["bg"]
    fg = palette["fg"]

    # Derive harmony colors from accent (these drive token scopes)
    tri = triad(accent)
    spl = split_complementary(accent)
    ana = analogous(accent)
    com = complementary(accent)

    com_col = darken(accent, 0.2)
    str_col = ana[2]
    num_col = com[1]
    func_col = tri[1]
    class_col = tri[2]
    type_col = tri[2]
    param_col = ana[2]
    prop_col = spl[1]
    regex_col = spl[2]

    # Auto-fix token contrast so dark tokens stay readable on dark bgs.
    # Thresholds: ≥4.5 for "text" tokens (string, num, keyword), ≥3.0 for
    # "decorative" tokens (comment, function, class, type, param, prop, regex).
    # Auto-fix is direction-aware: lighten if bg is dark, darken if bg is light.
    is_light_bg = _is_light_bg(bg)

    def _ensure_token(c: str, target_ratio: float) -> str:
        if wcag_ratio(c, bg) >= target_ratio:
            return c
        # Try lightening first if bg is dark, darkening if bg is light.
        order = (lighten, darken) if not is_light_bg else (darken, lighten)
        for fn in order:
            for step in range(1, 16):
                candidate = fn(c, step * 0.05)
                if wcag_ratio(candidate, bg) >= target_ratio:
                    return candidate
        return c

    com_col = _ensure_token(com_col, 3.0)
    str_col = _ensure_token(str_col, 4.5)
    num_col = _ensure_token(num_col, 4.5)
    func_col = _ensure_token(func_col, 3.0)
    class_col = _ensure_token(class_col, 3.0)
    type_col = _ensure_token(type_col, 3.0)
    param_col = _ensure_token(param_col, 3.0)
    prop_col = _ensure_token(prop_col, 3.0)
    regex_col = _ensure_token(regex_col, 3.0)

    # UI helpers
    is_light = _is_light_bg(bg)
    sidebar_bg = lighten(bg, 0.05) if is_light else darken(bg, 0.05)
    sidebar_bg_dark = darken(bg, 0.05) if not is_light else bg
    line_bg = darken(bg, 0.05) if not is_light else lighten(bg, 0.05)

    # Auto-correct editor.foreground vs editor.background to AA FIRST.
    fg = _ensure_contrast(fg, bg, 4.5)
    # And accent (keyword) vs bg
    accent = _ensure_contrast(accent, bg, 4.5)

    # Now pick contrasting fgs for status bar and badge (accent is final).
    def _pick_contrast_fg(against: str, candidates: list[str]) -> str:
        """Pick the candidate with the best WCAG ratio against `against`.
        Always returns something, even if no candidate passes 4.5."""
        best = candidates[0]
        best_ratio = wcag_ratio(best, against)
        for c in candidates:
            r = wcag_ratio(c, against)
            if r > best_ratio:
                best, best_ratio = c, r
            if r >= 4.5:
                return c
        return best

    status_fg = _pick_contrast_fg(accent, [bg, fg, "#FFFFFF", "#000000"])
    # Activity bar badge: accent bg, must pick a contrasting fg
    activity_badge_fg = _pick_contrast_fg(accent, [bg, fg, "#FFFFFF", "#000000"])

    # Selection highlight alpha helpers
    def _alpha(c: str, alpha: str) -> str:
        return _a(c, alpha)

    colors = {
        # ---- Editor core ----
        "editor.background": bg,
        "editor.foreground": fg,
        "editorCursor.foreground": accent,
        "editor.lineHighlightBackground": line_bg,
        "editor.lineHighlightBorder": _alpha(selection, "30"),
        "editor.selectionBackground": _alpha(selection, "60"),
        "editor.selectionHighlightBackground": _alpha(selection, "30"),
        "editor.inactiveSelectionBackground": _alpha(selection, "40"),
        "editor.wordHighlightBackground": _alpha(selection, "25"),
        "editor.wordHighlightStrongBackground": _alpha(selection, "40"),
        "editor.wordHighlightBorder": _alpha(selection, "60"),
        "editor.findMatchBackground": _alpha(selection, "50"),
        "editor.findMatchHighlightBackground": _alpha(selection, "30"),
        "editor.findMatchBorder": selection,
        "editor.linkedEditingBackground": _alpha(accent, "30"),
        "editor.rangeHighlightBackground": _alpha(selection, "20"),
        "editor.hoverHighlightBackground": _alpha(accent, "25"),
        "editorBracketMatch.background": _alpha(accent, "40"),
        "editorBracketMatch.border": accent,
        "editorIndentGuide.background": _alpha(fg, "20"),
        "editorIndentGuide.activeBackground": _alpha(selection, "60"),
        "editorWhitespace.foreground": _alpha(fg, "40"),
        "editor.foldBackground": _alpha(selection, "20"),
        "editorGutter.background": bg,
        "editorGutter.foreground": _alpha(fg, "60"),
        "editorGutter.modifiedBackground": type_col,
        "editorGutter.addedBackground": func_col,
        "editorGutter.deletedBackground": selection,
        "editorLineNumber.foreground": _alpha(fg, "60"),
        "editorLineNumber.activeForeground": fg,
        "editorRuler.foreground": _alpha(fg, "20"),
        "editorOverviewRuler.border": _alpha(selection, "60"),
        "editorError.foreground": selection,
        "editorError.background": _alpha(selection, "30"),
        "editorWarning.foreground": type_col,
        "editorWarning.background": _alpha(type_col, "30"),
        "editorInfo.foreground": func_col,
        "editorInfo.background": _alpha(func_col, "30"),
        "editorMarkerNavigation.background": _alpha(fg, "10"),
        "editorMarkerNavigationError.background": _alpha(selection, "60"),
        "editorMarkerNavigationWarning.background": _alpha(type_col, "60"),
        "editorMarkerNavigationInfo.background": _alpha(func_col, "60"),
        "editorSuggestWidget.background": sidebar_bg,
        "editorSuggestWidget.border": _alpha(fg, "30"),
        "editorSuggestWidget.foreground": fg,
        "editorSuggestWidget.highlightForeground": accent,
        "editorSuggestWidget.selectedBackground": _alpha(selection, "30"),
        "editorHoverWidget.background": sidebar_bg,
        "editorHoverWidget.border": _alpha(fg, "30"),
        "editorHoverWidget.foreground": fg,
        "editorHoverWidget.statusBarBackground": bg,
        "editorWidget.background": sidebar_bg,
        "editorWidget.border": _alpha(fg, "30"),
        "editorWidget.resizeBorder": selection,
        "editorCodeLens.foreground": _alpha(fg, "60"),
        "editorLightBulb.foreground": type_col,
        "editorLightBulbAutoFix.foreground": func_col,

        # ---- Workbench top-level ----
        "focusBorder": _alpha(selection, "60"),
        "foreground": fg,
        "disabledForeground": _alpha(fg, "50"),
        "descriptionForeground": _alpha(fg, "70"),
        "scrollbar.shadow": _alpha("#000000", "30"),
        "scrollbarSlider.background": _alpha(fg, "20"),
        "scrollbarSlider.hoverBackground": _alpha(fg, "30"),
        "scrollbarSlider.activeBackground": accent,
        "badge.background": accent,
        "badge.foreground": activity_badge_fg,
        "titleBar.activeBackground": bg,
        "titleBar.activeForeground": fg,
        "titleBar.inactiveBackground": sidebar_bg,
        "titleBar.inactiveForeground": _alpha(fg, "50"),

        # ---- Activity bar ----
        "activityBar.background": bg,
        "activityBar.foreground": fg,
        "activityBar.inactiveForeground": _alpha(fg, "50"),
        "activityBarBadge.background": accent,
        "activityBarBadge.foreground": activity_badge_fg,

        # ---- Side bar ----
        "sideBar.background": sidebar_bg,
        "sideBar.foreground": fg,
        "sideBarTitle.foreground": fg,
        "sideBarSectionHeader.background": bg,
        "sideBarSectionHeader.foreground": accent,
        "sideBarSectionHeader.border": _alpha(fg, "20"),

        # ---- Status bar ----
        "statusBar.background": accent,
        "statusBar.foreground": status_fg,
        "statusBar.noFolderBackground": accent,
        "statusBar.debuggingBackground": selection,
        "statusBarItem.activeBackground": _alpha(selection, "30"),
        "statusBarItem.hoverBackground": _alpha(fg, "15"),
        "statusBarItem.remoteBackground": func_col,

        # ---- Tabs ----
        "tab.activeBackground": bg,
        "tab.activeForeground": fg,
        "tab.activeBorder": accent,
        "tab.activeBorderTop": accent,
        "tab.inactiveBackground": sidebar_bg,
        "tab.inactiveForeground": _alpha(fg, "60"),
        "tab.border": _alpha(fg, "10"),
        "tab.unfocusedActiveBackground": bg,
        "tab.unfocusedInactiveBackground": sidebar_bg_dark,

        # ---- Panel ----
        "panel.background": bg,
        "panel.border": _alpha(fg, "20"),
        "panelTitle.activeBorder": accent,
        "panelTitle.activeForeground": fg,
        "panelTitle.inactiveForeground": _alpha(fg, "50"),
        "panelSection.background": sidebar_bg,
        "panelSectionHeader.background": bg,
        "panelSectionHeader.foreground": fg,
        "panelSection.border": _alpha(fg, "20"),

        # ---- Menu ----
        "menu.background": sidebar_bg,
        "menu.foreground": fg,
        "menu.selectionBackground": _alpha(selection, "30"),
        "menu.selectionForeground": fg,
        "menu.selectionBorder": accent,
        "menu.separatorBackground": _alpha(fg, "20"),
        "menu.border": _alpha(fg, "30"),

        # ---- Lists ----
        "list.background": sidebar_bg,
        "list.foreground": fg,
        "list.activeSelectionBackground": _alpha(selection, "40"),
        "list.activeSelectionForeground": fg,
        "list.inactiveSelectionBackground": _alpha(fg, "15"),
        "list.inactiveSelectionForeground": _alpha(fg, "80"),
        "list.hoverBackground": _alpha(fg, "10"),
        "list.hoverForeground": fg,
        "list.highlightForeground": accent,
        "list.focusBackground": _alpha(selection, "30"),
        "list.focusForeground": fg,
        "list.dropBackground": _alpha(selection, "30"),

        # ---- Buttons ----
        "button.background": accent,
        "button.foreground": activity_badge_fg,
        "button.hoverBackground": lighten(accent, 0.1) if not is_light else darken(accent, 0.1),
        "button.border": accent,
        "button.secondaryBackground": _alpha(fg, "20"),
        "button.secondaryForeground": fg,
        "button.secondaryHoverBackground": _alpha(fg, "30"),

        # ---- Inputs ----
        "input.background": bg,
        "input.foreground": fg,
        "input.border": _alpha(fg, "30"),
        "input.placeholderForeground": _alpha(fg, "50"),
        "inputOption.activeBackground": accent,
        "inputOption.activeBorder": accent,
        "inputOption.activeForeground": activity_badge_fg,
        "inputOption.hoverBackground": _alpha(fg, "20"),
        "inputValidation.errorBackground": _alpha(selection, "40"),
        "inputValidation.errorForeground": selection,
        "inputValidation.warningBackground": _alpha(type_col, "40"),
        "inputValidation.warningForeground": type_col,
        "inputValidation.infoBackground": _alpha(func_col, "40"),
        "inputValidation.infoForeground": func_col,

        # ---- Dropdown / Checkbox ----
        "dropdown.background": bg,
        "dropdown.foreground": fg,
        "dropdown.border": _alpha(fg, "30"),
        "checkbox.background": bg,
        "checkbox.foreground": fg,
        "checkbox.border": _alpha(fg, "30"),
        "checkbox.checkedBackground": accent,
        "checkbox.checkedForeground": activity_badge_fg,

        # ---- Progress / Notification ----
        "progressBar.background": accent,
        "notificationCenter.background": sidebar_bg,
        "notificationCenter.border": _alpha(fg, "30"),
        "notificationCenterHeader.background": sidebar_bg,
        "notificationCenterHeader.foreground": fg,
        "notifications.background": sidebar_bg,
        "notifications.border": _alpha(fg, "30"),
        "notifications.foreground": fg,
        "notifications.infoIcon": func_col,
        "notifications.warningIcon": type_col,
        "notifications.errorIcon": selection,
        "notifications.infoBackground": _alpha(func_col, "30"),
        "notifications.warningBackground": _alpha(type_col, "30"),
        "notifications.errorBackground": _alpha(selection, "30"),

        # ---- Breadcrumb / Settings ----
        "breadcrumb.background": sidebar_bg,
        "breadcrumb.foreground": _alpha(fg, "60"),
        "breadcrumb.focusForeground": fg,
        "breadcrumb.activeSelectionForeground": accent,
        "breadcrumbPicker.background": sidebar_bg,
        "settings.headerForeground": accent,
        "settings.modifiedItemIndicator": selection,
        "settings.inactiveModifiedItemIndicator": _alpha(fg, "50"),
        "settings.dropdownBackground": bg,
        "settings.dropdownForeground": fg,
        "settings.dropdownBorder": _alpha(fg, "30"),
        "settings.textInputBackground": bg,
        "settings.textInputForeground": fg,
        "settings.textInputBorder": _alpha(fg, "30"),
        "settings.numberInputBackground": bg,
        "settings.numberInputForeground": fg,
        "settings.numberInputBorder": _alpha(fg, "30"),
        "settings.checkboxBackground": bg,
        "settings.checkboxForeground": fg,
        "settings.checkboxBorder": _alpha(fg, "30"),
        "settings.rowHoverBackground": _alpha(fg, "10"),

        # ---- Minimap ----
        "minimap.background": bg,
        "minimap.foreground": _alpha(fg, "50"),
        "minimap.selectionHighlight": _alpha(selection, "60"),
        "minimap.findMatchHighlight": _alpha(selection, "80"),
        "minimap.errorHighlight": selection,
        "minimap.warningHighlight": type_col,
        "minimapSlider.background": _alpha(fg, "20"),
        "minimapSlider.hoverBackground": _alpha(fg, "30"),
        "minimapSlider.activeBackground": accent,

        # ---- Peek view ----
        "peekView.background": sidebar_bg,
        "peekView.border": _alpha(fg, "30"),
        "peekViewEditor.background": sidebar_bg,
        "peekViewEditor.matchHighlightBackground": _alpha(accent, "40"),
        "peekViewEditorGutter.background": bg,
        "peekViewResult.background": bg,
        "peekViewResult.fileBackground": bg,
        "peekViewResult.lineForeground": fg,
        "peekViewResult.matchHighlightBackground": _alpha(accent, "40"),
        "peekViewResult.selectionBackground": _alpha(selection, "40"),
        "peekViewResult.selectionForeground": fg,
        "peekViewTitle.background": sidebar_bg,
        "peekViewTitle.foreground": fg,
        "peekViewTitleDescription.foreground": _alpha(fg, "60"),
        "peekViewTitleLabel.foreground": accent,

        # ---- Diff editor ----
        "diffEditor.background": bg,
        "diffEditor.border": _alpha(fg, "20"),
        "diffEditor.diagonalFill": _alpha(accent, "20"),
        "diffEditor.insertedTextBackground": _alpha(func_col, "30"),
        "diffEditor.removedTextBackground": _alpha(selection, "30"),
        "diffEditorGutter.insertedLineBackground": _alpha(func_col, "60"),
        "diffEditorGutter.removedLineBackground": _alpha(selection, "60"),
        "diffEditor.insertedLineBackground": _alpha(func_col, "20"),
        "diffEditor.removedLineBackground": _alpha(selection, "20"),

        # ---- Merge ----
        "merge.currentHeaderBackground": _alpha(func_col, "40"),
        "merge.incomingHeaderBackground": _alpha(selection, "40"),
        "merge.currentContentBackground": _alpha(func_col, "15"),
        "merge.incomingContentBackground": _alpha(selection, "15"),
        "merge.border": _alpha(fg, "30"),

        # ---- Git decorations ----
        "gitDecoration.addedResourceForeground": func_col,
        "gitDecoration.modifiedResourceForeground": type_col,
        "gitDecoration.deletedResourceForeground": selection,
        "gitDecoration.untrackedResourceForeground": accent,
        "gitDecoration.ignoredResourceForeground": _alpha(fg, "50"),
        "gitDecoration.conflictingResourceForeground": selection,
        "gitDecoration.submoduleResourceForeground": str_col,

        # ---- Charts ----
        "charts.foreground": fg,
        "charts.lines": _alpha(fg, "30"),
        "charts.blue": func_col,
        "charts.green": func_col,
        "charts.yellow": type_col,
        "charts.orange": type_col,
        "charts.purple": accent,
        "charts.red": selection,

        # ---- Welcome / Walkthrough ----
        "welcomePage.background": bg,
        "welcomePage.buttonBackground": accent,
        "welcomePage.buttonHoverBackground": lighten(accent, 0.1) if not is_light else darken(accent, 0.1),
        "welcomePage.buttonForeground": activity_badge_fg,
        "welcomePage.tileBackground": sidebar_bg,
        "welcomePage.tileHoverBackground": _alpha(fg, "10"),
        "welcomePage.tileBorder": _alpha(fg, "20"),
        "walkThrough.embeddedEditorBackground": bg,

        # ---- Tree ----
        "tree.indentGuidesStroke": _alpha(fg, "30"),
        "tree.tableColumnsBorder": _alpha(fg, "30"),
        "tree.tableOddRowsBackground": _alpha(fg, "10"),

        # ---- Text styles ----
        "textLink.foreground": accent,
        "textLink.activeForeground": selection,
        "textBlockQuote.background": _alpha(fg, "10"),
        "textBlockQuote.border": accent,
        "textPreformat.foreground": func_col,
        "textSeparator.foreground": _alpha(fg, "40"),

        # ---- Keybinding labels ----
        "keybindingLabel.background": _alpha(fg, "20"),
        "keybindingLabel.foreground": fg,
        "keybindingLabel.border": _alpha(fg, "30"),
        "keybindingLabel.bottomBorder": accent,

        # ---- Terminal ----
        "terminal.background": bg,
        "terminal.foreground": fg,
        "terminalCursor.background": bg,
        "terminalCursor.foreground": accent,
        "terminal.selectionBackground": _alpha(selection, "40"),
        "terminal.selectionForeground": fg,
        "terminal.border": _alpha(fg, "20"),
        "terminal.findMatchBackground": _alpha(selection, "50"),
        "terminal.findMatchHighlightBackground": _alpha(selection, "30"),
        "terminal.hoverHighlightBackground": _alpha(accent, "25"),
        "terminal.dropBackground": _alpha(selection, "30"),
    }

    # Terminal ANSI 16 — derive from palette for consistency
    bg_rgb = _hex_to_rgb(bg)
    fg_rgb = _hex_to_rgb(fg)
    sel_rgb = _hex_to_rgb(selection)
    # Black = darkest readable (usually bg darken 0.5 for dark, or near-black for light)
    if is_light:
        ansi_black = "#000000"
        ansi_bright_black = _rgb_to_hex(
            **{k: v + (v * 0.3) for k, v in zip("rgb", bg_rgb)}
        ) if False else _rgb_to_hex(bg_rgb[0] * 0.6, bg_rgb[1] * 0.6, bg_rgb[2] * 0.6)
        ansi_white = fg
        ansi_bright_white = darken(fg, 0.05)
        ansi_green = com[1]  # complementary of accent
        ansi_yellow = type_col
        ansi_blue = func_col
        ansi_magenta = accent
        ansi_cyan = str_col
        ansi_red = selection
        # Brights = lighten by 0.15
    else:
        ansi_black = "#000000"
        ansi_bright_black = _alpha(fg, "30")[:7] if len(_alpha(fg, "30")) >= 7 else darken(fg, 0.2)
        ansi_white = fg
        ansi_bright_white = lighten(fg, 0.1)
        ansi_red = selection
        ansi_green = com[1]
        ansi_yellow = type_col
        ansi_blue = func_col
        ansi_magenta = accent
        ansi_cyan = str_col

    def _bright(c: str) -> str:
        return lighten(c, 0.15) if not is_light else darken(c, 0.15)

    colors.update({
        "terminal.ansiBlack": ansi_black,
        "terminal.ansiRed": ansi_red,
        "terminal.ansiGreen": ansi_green,
        "terminal.ansiYellow": ansi_yellow,
        "terminal.ansiBlue": ansi_blue,
        "terminal.ansiMagenta": ansi_magenta,
        "terminal.ansiCyan": ansi_cyan,
        "terminal.ansiWhite": ansi_white,
        "terminal.ansiBrightBlack": ansi_bright_black,
        "terminal.ansiBrightRed": _bright(ansi_red),
        "terminal.ansiBrightGreen": _bright(ansi_green),
        "terminal.ansiBrightYellow": _bright(ansi_yellow),
        "terminal.ansiBrightBlue": _bright(ansi_blue),
        "terminal.ansiBrightMagenta": _bright(ansi_magenta),
        "terminal.ansiBrightCyan": _bright(ansi_cyan),
        "terminal.ansiBrightWhite": ansi_bright_white,
    })

    # tokenColors
    token_colors = [
        # Comments
        {"scope": "comment", "settings": {"foreground": com_col, "fontStyle": "italic"}},
        {"scope": "comment.line", "settings": {"foreground": com_col, "fontStyle": "italic"}},
        {"scope": "comment.block", "settings": {"foreground": com_col, "fontStyle": "italic"}},
        {"scope": "comment.documentation", "settings": {"foreground": com_col, "fontStyle": "italic"}},
        # Strings
        {"scope": "string", "settings": {"foreground": str_col}},
        {"scope": "string.quoted", "settings": {"foreground": str_col}},
        {"scope": "string.template", "settings": {"foreground": str_col}},
        {"scope": "string.interpolated", "settings": {"foreground": str_col}},
        {"scope": "string.regexp", "settings": {"foreground": regex_col}},
        # Constants
        {"scope": "constant.numeric", "settings": {"foreground": num_col}},
        {"scope": "constant.character", "settings": {"foreground": num_col}},
        {"scope": "constant.character.escape", "settings": {"foreground": regex_col}},
        {"scope": "constant.language", "settings": {"foreground": num_col, "fontStyle": "italic"}},
        {"scope": "variable.other.constant", "settings": {"foreground": num_col}},
        # Keywords / storage
        {"scope": "keyword", "settings": {"foreground": accent, "fontStyle": "bold"}},
        {"scope": "keyword.control", "settings": {"foreground": accent, "fontStyle": "bold"}},
        {"scope": "keyword.operator", "settings": {"foreground": accent}},
        {"scope": "keyword.other", "settings": {"foreground": accent}},
        {"scope": "storage", "settings": {"foreground": accent}},
        {"scope": "storage.modifier", "settings": {"foreground": accent, "fontStyle": "italic"}},
        {"scope": "storage.type", "settings": {"foreground": type_col, "fontStyle": "italic"}},
        # Entities
        {"scope": "entity.name.function", "settings": {"foreground": func_col}},
        {"scope": "entity.name.function.member", "settings": {"foreground": func_col}},
        {"scope": "entity.name.class", "settings": {"foreground": class_col, "fontStyle": "bold"}},
        {"scope": "entity.name.struct", "settings": {"foreground": class_col, "fontStyle": "bold"}},
        {"scope": "entity.name.type", "settings": {"foreground": type_col}},
        {"scope": "entity.name.tag", "settings": {"foreground": accent}},
        {"scope": "entity.other.attribute-name", "settings": {"foreground": param_col}},
        # Support
        {"scope": "support.function", "settings": {"foreground": func_col}},
        {"scope": "support.class", "settings": {"foreground": class_col}},
        {"scope": "support.type", "settings": {"foreground": type_col}},
        {"scope": "support.constant", "settings": {"foreground": type_col}},
        {"scope": "support.variable", "settings": {"foreground": type_col}},
        # Variables
        {"scope": "variable", "settings": {"foreground": fg}},
        {"scope": "variable.other.readwrite", "settings": {"foreground": fg}},
        {"scope": "variable.parameter", "settings": {"foreground": param_col, "fontStyle": "italic"}},
        {"scope": "variable.other.property", "settings": {"foreground": prop_col}},
        # Punctuation
        {"scope": "punctuation", "settings": {"foreground": _a(fg, "B0")}},
        {"scope": "punctuation.definition.string", "settings": {"foreground": str_col}},
        {"scope": "punctuation.definition.comment", "settings": {"foreground": com_col}},
        {"scope": "punctuation.definition.tag", "settings": {"foreground": accent}},
        {"scope": "punctuation.separator", "settings": {"foreground": _a(fg, "B0")}},
        # Invalid — use accent (always passes 4.5 vs bg), not selection.
        {"scope": "invalid", "settings": {"foreground": accent, "fontStyle": "bold underline"}},
        {"scope": "invalid.deprecated", "settings": {"foreground": accent, "fontStyle": "bold underline"}},
        {"scope": "invalid.illegal", "settings": {"foreground": accent, "fontStyle": "bold underline"}},
        # Markup
        {"scope": "markup.heading", "settings": {"foreground": accent, "fontStyle": "bold"}},
        {"scope": "markup.bold", "settings": {"foreground": fg, "fontStyle": "bold"}},
        {"scope": "markup.italic", "settings": {"foreground": fg, "fontStyle": "italic"}},
        {"scope": "markup.underline", "settings": {"foreground": fg, "fontStyle": "underline"}},
        {"scope": "markup.inline.raw", "settings": {"foreground": num_col}},
        {"scope": "markup.list.unnumbered", "settings": {"foreground": param_col}},
        {"scope": "markup.list.numbered", "settings": {"foreground": param_col}},
        {"scope": "markup.quote", "settings": {"foreground": com_col, "fontStyle": "italic"}},
        {"scope": "markup.deleted", "settings": {"foreground": accent, "fontStyle": "strikethrough"}},
        {"scope": "markup.inserted", "settings": {"foreground": func_col}},
        {"scope": "markup.changed", "settings": {"foreground": type_col}},
        # Meta / diff
        {"scope": "meta.diff", "settings": {"foreground": param_col}},
        {"scope": "meta.diff.header", "settings": {"foreground": accent}},
        {"scope": "meta.range", "settings": {"foreground": type_col}},
        # Emphasis
        {"scope": "emphasis.strong", "settings": {"foreground": fg, "fontStyle": "bold"}},
        {"scope": "emphasis.italic", "settings": {"foreground": fg, "fontStyle": "italic"}},
        {"scope": "entity.name.link", "settings": {"foreground": str_col, "fontStyle": "underline"}},
    ]

    display_name = f"Themixir {color_name.capitalize()}{DISPLAY_SUFFIX[variant]}"
    ui_theme = UI_THEME[variant]
    theme_type = "light" if ui_theme == "vs" else "dark"

    return {
        "name": display_name,
        "type": theme_type,
        "colors": colors,
        "tokenColors": token_colors,
    }


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def generate_all() -> list[dict]:
    raw = json.loads((ROOT / "Themixir.json").read_text())
    meta = raw.pop("_meta", None)
    if not meta or meta.get("schema_version") != 2:
        raise ValueError("Themixir.json missing _meta.schema_version=2")

    palettes: dict[str, dict] = raw  # type: ignore

    def _build(color_variant: tuple[str, str]) -> dict:
        color_name, variant = color_variant
        base = palettes[color_name]
        vp = base[variant]
        full = {**base, **vp}
        return build_theme(color_name, variant, full)

    pairs = [(c, v) for c in palettes for v in VARIANTS]
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(_build, pairs))


def write_themes(themes: list[dict]) -> list[dict]:
    """Write themes to themes/ and return the package.json manifest entries."""
    themes_dir = ROOT / "themes"
    themes_dir.mkdir(exist_ok=True)
    # Clear old themes first so deletions are honored
    for f in themes_dir.glob("*.json"):
        f.unlink()

    manifest: list[dict] = []
    for theme in themes:
        # Recover color_name and variant from the display name
        name = theme["name"]
        # name looks like "Themixir Red Solarized"
        stripped = name.replace("Themixir ", "")
        # Detect variant
        for v, suffix in DISPLAY_SUFFIX.items():
            if stripped.endswith(suffix):
                color_name = stripped[: -len(suffix)] if suffix else stripped
                color_key = color_name.lower().replace(" ", "_")
                filename = f"{color_key}{FILE_SUFFIX[v]}.json"
                ui_theme = UI_THEME[v]
                break
        else:
            raise ValueError(f"Cannot parse display name: {name}")

        (themes_dir / filename).write_text(json.dumps(theme, indent=2))
        manifest.append({
            "label": name,
            "uiTheme": ui_theme,
            "path": f"./themes/{filename}",
        })
    return manifest


def update_package_json(manifest: list[dict]) -> None:
    """Rewrite only contributes.themes in package.json, leave the rest alone."""
    pkg_path = ROOT / "package.json"
    pkg = json.loads(pkg_path.read_text())
    pkg["contributes"]["themes"] = manifest
    pkg_path.write_text(json.dumps(pkg, indent=2))


def main() -> None:
    themes = generate_all()
    manifest = write_themes(themes)
    update_package_json(manifest)
    print(f"Generated {len(themes)} themes (10 colors × 5 variants) and updated package.json")


if __name__ == "__main__":
    main()