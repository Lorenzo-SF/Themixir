#!/usr/bin/env python3
"""Themixir theme generator (schema v3).

Reads Themixir.json (schema v3): 10 base palettes × `selection`/`accent`.
Generates 5 variants per palette (solarized, light, normal, dark,
solarized_dark) with backgrounds tinted from the selection via alaja.

All colour math (harmonies, darken, lighten) is delegated to alaja so
that the token palette for each colour feels distinct instead of being
just a hue rotation. WCAG 2.1 ratios are validated and auto-corrected.

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
UI_THEME = {
    "solarized": "vs",
    "light": "vs",
    "normal": "vs-dark",
    "dark": "vs-dark",
    "solarized_dark": "vs-dark",
}
FILE_SUFFIX = {
    "solarized": "_solarized",
    "light": "_light",
    "normal": "",
    "dark": "_dark",
    "solarized_dark": "_solarized_dark",
}
DISPLAY_SUFFIX = {
    "solarized": " Solarized",
    "light": " Light",
    "normal": "",
    "dark": " Dark",
    "solarized_dark": " Solarized Dark",
}

# Fixed background and foreground for solarized variants (Solarized base palette).
SOLARIZED_BG = "#FDF6E3"
SOLARIZED_FG = "#586E75"
SOLARIZED_DARK_BG = "#002B36"
SOLARIZED_DARK_FG = "#93A1A1"

# Fixed neutral background for the "normal" variant (everyone likes VS Code dark+).
NORMAL_BG = "#1E1E1E"
NORMAL_FG = "#D4D4D4"

# Alaja steps used for `lighten`/`darken` to produce tinted bgs. 1..10.
LIGHTEN_STEPS = 7
DARKEN_STEPS = 7

# Token palette roles → which slot of the colour-family palette to use.
# Every role stays within the colour's own hue family: no complement,
# no triad+240°, no split+210°. Only lightness/hue ±30° variants of the
# base accent.
#
# `keyword` and `storage` use `lighter` (not `core`) so that an accent
# like saturated blue/green doesn't read as "everything is a keyword
# AND it's neon" — a common complaint against high-saturation themes.
# The accent is still used for chrome (statusBar, button, badge) so
# the colour identity is intact.
TOKEN_ROLE_TO_SLOT = {
    "keyword":              "lighter",
    "storage":              "lighter",
    "string":               "ana_plus",       # base +30° hue
    "string_regex":         "ana_minus",      # base -30° hue
    "number":               "lighter",        # base +30% lightness
    "function":             "ana_minus",      # base -30° hue
    "class":                "much_lighter",   # base +60% lightness
    "type":                 "darker",         # base -30% lightness
    "parameter":            "lighter",        # base +30% lightness
    "property":             "darker",         # base -30% lightness
    "constant_lang":        "ana_minus",      # base -30° hue
    "constant_char_escape": "ana_plus",       # base +30° hue
    "comment":              "much_darker",    # base -60% lightness (decorative)
}

# Cache alaja results so we don't pay subprocess cost twice.
_alaja_cache: dict[tuple, str | list[str]] = {}


# ----------------------------------------------------------------------
# Alaja wrappers
# ----------------------------------------------------------------------

def _alaja(*args: str) -> str:
    """Run alaja with the given args and return stdout."""
    cmd = [ALAJA, *args]
    key = tuple(args)
    if key in _alaja_cache:
        return _alaja_cache[key]  # type: ignore[return-value]
    # alaja is an Elixir script that needs HOME; other env vars don't matter.
    env = {
        "HOME": str(Path.home()),
        "NO_COLOR": "1",
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=15, env=env,
    )
    out = result.stdout.strip()
    _alaja_cache[key] = out
    return out


_HEX_RE = re.compile(r"#([0-9A-Fa-f]{6})\b")


def _extract_hexes(text: str) -> list[str]:
    """Pull every #RRGGBB hex out of alaja's table-formatted output."""
    return [f"#{m.upper()}" for m in _HEX_RE.findall(text)]


def alaja_color(hex_color: str) -> str:
    """Run `alaja color <hex>` and return the canonical hex."""
    out = _alaja("color", f"hex:{hex_color}", "--no-color", "--quiet")
    hexes = _extract_hexes(out)
    if not hexes:
        raise RuntimeError(f"alaja could not parse {hex_color}: {out!r}")
    return hexes[0]


def alaja_darken(hex_color: str, steps: int) -> str:
    """Run `alaja color <hex> --darken N` and return the result."""
    out = _alaja("color", f"hex:{hex_color}", "--darken", str(steps),
                 "--no-color", "--quiet")
    hexes = _extract_hexes(out)
    if not hexes:
        raise RuntimeError(f"alaja darken failed for {hex_color}: {out!r}")
    return hexes[0]


def alaja_lighten(hex_color: str, steps: int) -> str:
    """Run `alaja color <hex> --lighten N` and return the result."""
    out = _alaja("color", f"hex:{hex_color}", "--lighten", str(steps),
                 "--no-color", "--quiet")
    hexes = _extract_hexes(out)
    if not hexes:
        raise RuntimeError(f"alaja lighten failed for {hex_color}: {out!r}")
    return hexes[0]


_HARMONY_ALIASES = {
    "analogous": "analogous",
    "triad": "triad",
    "complementary": "complementary",
    "split": "split_complementary",
    "split_complementary": "split_complementary",
    "square": "square",
    "compound": "compound",
    "monochromatic": "monochromatic",
}


def alaja_harmony(hex_color: str, harmony: str) -> list[str]:
    """Run `alaja color <hex> --harmony TYPE` and return a list of hexes.

    Returns [base, ...harmonies] (base is always index 0).
    """
    h = _HARMONY_ALIASES.get(harmony, harmony)
    out = _alaja("color", f"hex:{hex_color}", "--harmony", h,
                 "--no-color", "--quiet")
    hexes = _extract_hexes(out)
    if not hexes:
        raise RuntimeError(f"alaja harmony {harmony!r} failed for "
                           f"{hex_color}: {out!r}")
    return hexes


# ----------------------------------------------------------------------
# WCAG validation (pure Python — fast)
# ----------------------------------------------------------------------

def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r = _srgb_to_linear(int(h[0:2], 16) / 255)
    g = _srgb_to_linear(int(h[2:4], 16) / 255)
    b = _srgb_to_linear(int(h[4:6], 16) / 255)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag_ratio(fg: str, bg: str) -> float:
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _ensure_contrast(fg: str, bg: str, min_ratio: float = 4.5) -> str:
    if wcag_ratio(fg, bg) >= min_ratio:
        return fg
    for step in range(1, 11):
        candidate = alaja_darken(fg, step)
        if wcag_ratio(candidate, bg) >= min_ratio:
            return candidate
    for step in range(1, 11):
        candidate = alaja_lighten(fg, step)
        if wcag_ratio(candidate, bg) >= min_ratio:
            return candidate
    return fg


# ----------------------------------------------------------------------
# Theme builder
# ----------------------------------------------------------------------

def _alpha(hex_color: str, alpha_hex: str) -> str:
    """Append 2-digit alpha to a 6-digit hex, preserving the leading #.

    e.g. _alpha('#5D93CD', '30') -> '#5D93CD30', not '5D93CD30'.
    """
    return "#" + hex_color.lstrip("#") + alpha_hex.upper()


# Font-style policy:
#
#   Light themes: coloured tokens on a tinted light bg wash out unless
#   they carry weight. We use BOLD for keyword / storage / function /
#   class / type / parameter — they're the scopes the user reads
#   every day, and bold makes the colour pop. Italic is reserved for
#   things that should be visually soft (comments, deprecated).
#
#   Dark themes: a saturated accent + bold on every keyword reads as
#   neon fever dream. Italic gives the keyword visual weight without
#   stealing focus from the colour. `keyword.control` (if/for/while)
#   keeps bold because those deserve emphasis.
def _ts(role: str, is_light: bool) -> str | None:
    if role in ("comment", "comment.line", "comment.block", "comment.documentation"):
        return "italic"
    if role in ("keyword.control", "entity.name.class", "entity.name.struct",
                "markup.heading"):
        return "bold"
    if role in ("keyword", "storage", "storage.modifier"):
        return "bold" if is_light else "italic"
    if role in ("entity.name.function", "entity.name.type"):
        return "bold" if is_light else None
    if role in ("storage.type", "variable.parameter"):
        return "bold" if is_light else "italic"
    if role == "markup.bold":
        return "bold"
    if role == "markup.italic":
        return "italic"
    if role == "markup.underline":
        return "underline"
    if role == "markup.deleted":
        return "strikethrough"
    if role in ("entity.name.link",):
        return "underline"
    if role in ("emphasis.strong",):
        return "bold"
    if role in ("emphasis.italic",):
        return "italic"
    return None


def _best_contrast_fg(against: str, candidates: list[str]) -> str:
    """Return the candidate with the best WCAG ratio against `against`."""
    best, best_ratio = candidates[0], wcag_ratio(candidates[0], against)
    for c in candidates:
        r = wcag_ratio(c, against)
        if r > best_ratio:
            best, best_ratio = c, r
        if r >= 4.5:
            return c
    return best


def _build_variant_bgfg(variant: str, selection: str) -> tuple[str, str]:
    """Compute the bg/fg pair for a variant using alaja.

    - solarized / solarized_dark: fixed Solarized base/03 palette (no tint)
    - light / dark: bg tinted from selection via alaja lighten/darken;
      fg computed to maintain contrast (≥4.5) with bg, using alaja for tone
    - normal: neutral #1E1E1E + #D4D4D4
    """
    if variant == "solarized":
        return SOLARIZED_BG, SOLARIZED_FG
    if variant == "solarized_dark":
        return SOLARIZED_DARK_BG, SOLARIZED_DARK_FG
    if variant == "normal":
        return NORMAL_BG, NORMAL_FG

    if variant == "light":
        bg = alaja_lighten(selection, LIGHTEN_STEPS)
        # fg: dark, tinted with selection for harmony
        fg = alaja_darken(selection, DARKEN_STEPS)
        # ensure contrast, otherwise nudge darker
        for _ in range(8):
            if wcag_ratio(fg, bg) >= 4.5:
                break
            fg = alaja_darken(fg, 1)
        return bg, fg

    if variant == "dark":
        bg = alaja_darken(selection, DARKEN_STEPS)
        fg = alaja_lighten(selection, LIGHTEN_STEPS)
        for _ in range(8):
            if wcag_ratio(fg, bg) >= 4.5:
                break
            fg = alaja_lighten(fg, 1)
        return bg, fg

    raise ValueError(f"unknown variant {variant!r}")


def _build_family_palette(accent: str) -> dict[str, str]:
    """Build a 7-colour palette where every colour stays within the accent's
    own hue family (no complement, no triad+240°). This prevents a green
    theme from accidentally producing red/magenta tokens.

    Slots:
      core          — the accent itself (keywords, storage)
      lighter       — accent lightened 3 alaja steps (~+30% L)
      darker        — accent darkened 3 alaja steps (~-30% L)
      much_lighter  — accent lightened 6 alaja steps (~+60% L)
      much_darker   — accent darkened 6 alaja steps (~-60% L)
      ana_plus      — analogous hue +30° (same lightness)
      ana_minus     — analogous hue -30° (same lightness)
    """
    # analogous returns [base, base-30°, base+30°]; alaja's column order
    # for analogous is "Analogous₁" first (base-30°) then "Analogous₂" (base+30°).
    ana = alaja_harmony(accent, "analogous")
    ana_minus = ana[1] if len(ana) > 1 else accent
    ana_plus = ana[2] if len(ana) > 2 else accent
    return {
        "core":         accent,
        "lighter":      alaja_lighten(accent, 3),
        "darker":       alaja_darken(accent, 3),
        "much_lighter": alaja_lighten(accent, 6),
        "much_darker":  alaja_darken(accent, 6),
        "ana_plus":     ana_plus,
        "ana_minus":    ana_minus,
    }


# Roles that need WCAG-AA (≥4.5) against editor background.
CRITICAL_TOKEN_ROLES = (
    "keyword", "storage", "string", "string_regex", "number", "function",
    "class", "type", "parameter", "property",
    "constant_lang", "constant_char_escape",
)
# Roles that only need decorative contrast (≥3.0).
DECORATIVE_TOKEN_ROLES = ("comment",)


def _tint_variant_with_token_fix(
    bg: str, fg: str, accent: str, selection: str,
) -> tuple[str, str, str, dict[str, str]]:
    """Compute token colors for a variant, auto-fixing WCAG ratios.

    Returns (bg, fg, accent, token_map)."""
    # Base accent fix vs bg
    accent = _ensure_contrast(accent, bg, 4.5)
    fg = _ensure_contrast(fg, bg, 4.5)

    # Build an in-family palette of 7 colour slots, all derived from accent.
    # Every token role maps to one slot, so no token ever escapes the
    # colour family (no red tokens in a green theme).
    palette = _build_family_palette(accent)
    tokens: dict[str, str] = {role: palette[slot]
                               for role, slot in TOKEN_ROLE_TO_SLOT.items()}

    # Direction-aware auto-fix: try both directions and keep the smaller
    # adjustment that crosses the target threshold.
    def _fix(c: str, target: float) -> str:
        if wcag_ratio(c, bg) >= target:
            return c
        # Try lightening first (most common case for dark themes).
        for step in range(1, 11):
            candidate = alaja_lighten(c, step)
            if wcag_ratio(candidate, bg) >= target:
                return candidate
        # Fall back to darkening.
        for step in range(1, 11):
            candidate = alaja_darken(c, step)
            if wcag_ratio(candidate, bg) >= target:
                return candidate
        # Last resort: pure white or black depending on bg luminance.
        return "#FFFFFF" if _relative_luminance(bg) < 0.5 else "#000000"

    # Critical tokens: ≥4.5
    for role in CRITICAL_TOKEN_ROLES:
        if role in tokens:
            tokens[role] = _fix(tokens[role], 4.5)
    # Comments: ≥3.0 (decorative)
    for role in DECORATIVE_TOKEN_ROLES:
        if role in tokens:
            tokens[role] = _fix(tokens[role], 3.0)

    return bg, fg, accent, tokens


def _is_light_bg(bg_hex: str) -> bool:
    return _relative_luminance(bg_hex) > 0.5


def build_theme(color_name: str, variant: str, palette: dict) -> dict:
    selection = palette["selection"]
    accent = palette["accent"]

    bg, fg = _build_variant_bgfg(variant, selection)
    bg, fg, accent, tokens = _tint_variant_with_token_fix(
        bg, fg, accent, selection)

    is_light = _is_light_bg(bg)
    sidebar_bg = alaja_lighten(bg, 1) if is_light else alaja_darken(bg, 1)
    line_bg = alaja_darken(bg, 1) if not is_light else alaja_lighten(bg, 1)

    status_fg = _best_contrast_fg(accent, [bg, fg, "#FFFFFF", "#000000"])
    activity_badge_fg = status_fg

    sel = selection

    colors = {
        # ---- Editor core ----
        "editor.background": bg,
        "editor.foreground": fg,
        "editorCursor.foreground": accent,
        "editor.lineHighlightBackground": line_bg,
        "editor.lineHighlightBorder": _alpha(sel, "30"),
        "editor.selectionBackground": _alpha(sel, "60"),
        "editor.selectionHighlightBackground": _alpha(sel, "30"),
        "editor.inactiveSelectionBackground": _alpha(sel, "40"),
        "editor.wordHighlightBackground": _alpha(sel, "25"),
        "editor.wordHighlightStrongBackground": _alpha(sel, "40"),
        "editor.wordHighlightBorder": _alpha(sel, "60"),
        "editor.findMatchBackground": _alpha(sel, "50"),
        "editor.findMatchHighlightBackground": _alpha(sel, "30"),
        "editor.findMatchBorder": sel,
        "editor.linkedEditingBackground": _alpha(accent, "30"),
        "editor.rangeHighlightBackground": _alpha(sel, "20"),
        "editor.hoverHighlightBackground": _alpha(accent, "25"),
        "editorBracketMatch.background": _alpha(accent, "40"),
        "editorBracketMatch.border": accent,
        "editorIndentGuide.background": _alpha(fg, "20"),
        "editorIndentGuide.activeBackground": _alpha(sel, "60"),
        "editorWhitespace.foreground": _alpha(fg, "40"),
        "editor.foldBackground": _alpha(sel, "20"),
        "editorGutter.background": bg,
        "editorGutter.foreground": _alpha(fg, "60"),
        "editorGutter.modifiedBackground": tokens["type"],
        "editorGutter.addedBackground": tokens["function"],
        "editorGutter.deletedBackground": sel,
        "editorLineNumber.foreground": _alpha(fg, "60"),
        "editorLineNumber.activeForeground": fg,
        "editorRuler.foreground": _alpha(fg, "20"),
        "editorOverviewRuler.border": _alpha(sel, "60"),
        "editorError.foreground": sel,
        "editorError.background": _alpha(sel, "30"),
        "editorWarning.foreground": tokens["type"],
        "editorWarning.background": _alpha(tokens["type"], "30"),
        "editorInfo.foreground": tokens["function"],
        "editorInfo.background": _alpha(tokens["function"], "30"),
        "editorMarkerNavigation.background": _alpha(fg, "10"),
        "editorMarkerNavigationError.background": _alpha(sel, "60"),
        "editorMarkerNavigationWarning.background": _alpha(tokens["type"], "60"),
        "editorMarkerNavigationInfo.background": _alpha(tokens["function"], "60"),
        "editorSuggestWidget.background": sidebar_bg,
        "editorSuggestWidget.border": _alpha(fg, "30"),
        "editorSuggestWidget.foreground": fg,
        "editorSuggestWidget.highlightForeground": accent,
        "editorSuggestWidget.selectedBackground": _alpha(sel, "30"),
        "editorHoverWidget.background": sidebar_bg,
        "editorHoverWidget.border": _alpha(fg, "30"),
        "editorHoverWidget.foreground": fg,
        "editorHoverWidget.statusBarBackground": bg,
        "editorWidget.background": sidebar_bg,
        "editorWidget.border": _alpha(fg, "30"),
        "editorWidget.resizeBorder": sel,
        "editorCodeLens.foreground": _alpha(fg, "60"),
        "editorLightBulb.foreground": tokens["type"],
        "editorLightBulbAutoFix.foreground": tokens["function"],

        # ---- Workbench top-level ----
        "focusBorder": _alpha(sel, "60"),
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
        # Every theme variant uses `accent` for the activity-bar icons so
        # the explorer / search / git / extensions buttons are visible
        # and clearly identify the theme colour. The active icon is one
        # shade brighter; inactive icons are dimmed with alpha so the
        # active one still stands out.
        "activityBar.background": bg,
        "activityBar.foreground": accent,
        "activityBar.activeForeground": alaja_lighten(accent, 1) if not is_light
                                         else alaja_darken(accent, 1),
        "activityBar.inactiveForeground": _alpha(accent, "60"),
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
        "statusBar.debuggingBackground": sel,
        "statusBarItem.activeBackground": _alpha(sel, "30"),
        "statusBarItem.hoverBackground": _alpha(fg, "15"),
        "statusBarItem.remoteBackground": tokens["function"],

        # ---- Tabs ----
        "tab.activeBackground": bg,
        "tab.activeForeground": fg,
        "tab.activeBorder": accent,
        "tab.activeBorderTop": accent,
        "tab.inactiveBackground": sidebar_bg,
        "tab.inactiveForeground": _alpha(fg, "60"),
        "tab.border": _alpha(fg, "10"),
        "tab.unfocusedActiveBackground": bg,
        "tab.unfocusedInactiveBackground": sidebar_bg,

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
        "menu.selectionBackground": _alpha(sel, "30"),
        "menu.selectionForeground": fg,
        "menu.selectionBorder": accent,
        "menu.separatorBackground": _alpha(fg, "20"),
        "menu.border": _alpha(fg, "30"),

        # ---- Lists ----
        "list.background": sidebar_bg,
        "list.foreground": fg,
        "list.activeSelectionBackground": _alpha(sel, "40"),
        "list.activeSelectionForeground": fg,
        "list.inactiveSelectionBackground": _alpha(fg, "15"),
        "list.inactiveSelectionForeground": _alpha(fg, "80"),
        "list.hoverBackground": _alpha(fg, "10"),
        "list.hoverForeground": fg,
        "list.highlightForeground": accent,
        "list.focusBackground": _alpha(sel, "30"),
        "list.focusForeground": fg,
        "list.dropBackground": _alpha(sel, "30"),

        # ---- Buttons ----
        "button.background": accent,
        "button.foreground": activity_badge_fg,
        "button.hoverBackground": alaja_lighten(accent, 1) if not is_light
                                  else alaja_darken(accent, 1),
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
        "inputValidation.errorBackground": _alpha(sel, "40"),
        "inputValidation.errorForeground": sel,
        "inputValidation.warningBackground": _alpha(tokens["type"], "40"),
        "inputValidation.warningForeground": tokens["type"],
        "inputValidation.infoBackground": _alpha(tokens["function"], "40"),
        "inputValidation.infoForeground": tokens["function"],

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
        "notifications.infoIcon": tokens["function"],
        "notifications.warningIcon": tokens["type"],
        "notifications.errorIcon": sel,
        "notifications.infoBackground": _alpha(tokens["function"], "30"),
        "notifications.warningBackground": _alpha(tokens["type"], "30"),
        "notifications.errorBackground": _alpha(sel, "30"),

        # ---- Breadcrumb / Settings ----
        "breadcrumb.background": sidebar_bg,
        "breadcrumb.foreground": _alpha(fg, "60"),
        "breadcrumb.focusForeground": fg,
        "breadcrumb.activeSelectionForeground": accent,
        "breadcrumbPicker.background": sidebar_bg,
        "settings.headerForeground": accent,
        "settings.modifiedItemIndicator": sel,
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
        "minimap.selectionHighlight": _alpha(sel, "60"),
        "minimap.findMatchHighlight": _alpha(sel, "80"),
        "minimap.errorHighlight": sel,
        "minimap.warningHighlight": tokens["type"],
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
        "peekViewResult.selectionBackground": _alpha(sel, "40"),
        "peekViewResult.selectionForeground": fg,
        "peekViewTitle.background": sidebar_bg,
        "peekViewTitle.foreground": fg,
        "peekViewTitleDescription.foreground": _alpha(fg, "60"),
        "peekViewTitleLabel.foreground": accent,

        # ---- Diff editor ----
        "diffEditor.background": bg,
        "diffEditor.border": _alpha(fg, "20"),
        "diffEditor.diagonalFill": _alpha(accent, "20"),
        "diffEditor.insertedTextBackground": _alpha(tokens["function"], "30"),
        "diffEditor.removedTextBackground": _alpha(sel, "30"),
        "diffEditorGutter.insertedLineBackground": _alpha(tokens["function"], "60"),
        "diffEditorGutter.removedLineBackground": _alpha(sel, "60"),
        "diffEditor.insertedLineBackground": _alpha(tokens["function"], "20"),
        "diffEditor.removedLineBackground": _alpha(sel, "20"),

        # ---- Merge ----
        "merge.currentHeaderBackground": _alpha(tokens["function"], "40"),
        "merge.incomingHeaderBackground": _alpha(sel, "40"),
        "merge.currentContentBackground": _alpha(tokens["function"], "15"),
        "merge.incomingContentBackground": _alpha(sel, "15"),
        "merge.border": _alpha(fg, "30"),

        # ---- Git decorations ----
        "gitDecoration.addedResourceForeground": tokens["function"],
        "gitDecoration.modifiedResourceForeground": tokens["type"],
        "gitDecoration.deletedResourceForeground": sel,
        "gitDecoration.untrackedResourceForeground": accent,
        "gitDecoration.ignoredResourceForeground": _alpha(fg, "50"),
        "gitDecoration.conflictingResourceForeground": sel,
        "gitDecoration.submoduleResourceForeground": tokens["string"],

        # ---- Charts ----
        "charts.foreground": fg,
        "charts.lines": _alpha(fg, "30"),
        "charts.blue": tokens["function"],
        "charts.green": tokens["function"],
        "charts.yellow": tokens["type"],
        "charts.orange": tokens["type"],
        "charts.purple": accent,
        "charts.red": sel,

        # ---- Welcome / Walkthrough ----
        "welcomePage.background": bg,
        "welcomePage.buttonBackground": accent,
        "welcomePage.buttonHoverBackground": alaja_lighten(accent, 1) if not is_light
                                            else alaja_darken(accent, 1),
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
        "textLink.activeForeground": sel,
        "textBlockQuote.background": _alpha(fg, "10"),
        "textBlockQuote.border": accent,
        "textPreformat.foreground": tokens["function"],
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
        "terminal.selectionBackground": _alpha(sel, "40"),
        "terminal.selectionForeground": fg,
        "terminal.border": _alpha(fg, "20"),
        "terminal.findMatchBackground": _alpha(sel, "50"),
        "terminal.findMatchHighlightBackground": _alpha(sel, "30"),
        "terminal.hoverHighlightBackground": _alpha(accent, "25"),
        "terminal.dropBackground": _alpha(sel, "30"),
    }

    # ---- Previously missing workbench colors (vscode defaults are red) ----
    # The user reported that error/warning markers (default red in VSCode)
    # leaked into many UI slots because we didn't override the defaults.
    # We now provide a complete override so no slot inherits the system red.
    extra_colors = {
        # Activity bar: focus / active states
        "activityBar.activeBackground": bg,
        "activityBar.activeBorder": accent,
        "activityBar.activeFocusBorder": accent,
        "activityBar.dropBackground": _alpha(sel, "30"),
        "activityBarBadge.foreground": activity_badge_fg,

        # Editor line numbers: error/warning/info/breakpoint markers
        "editorLineNumber.errorForeground": sel,
        "editorLineNumber.warningForeground": tokens["type"],
        "editorLineNumber.infoForeground": tokens["function"],
        "editorLineNumber.breakpointForeground": sel,
        "editorCursor.background": bg,

        # Breadcrumbs: focus state and active (hovered) state
        "breadcrumb.activeForeground": accent,
        "breadcrumbPicker.foreground": fg,
        "breadcrumbPicker.focusForeground": accent,

        # Tabs: hover, unfocused hover, modified borders
        "tab.hoverBackground": _alpha(accent, "15"),
        "tab.hoverBorder": accent,
        "tab.unfocusedHoverBackground": _alpha(accent, "10"),
        "tab.unfocusedActiveBorder": accent,
        "tab.unfocusedActiveBorderTop": accent,
        "tab.activeModifiedBorder": sel,
        "tab.inactiveModifiedBorder": _alpha(sel, "50"),
        "tab.lastPinnedBorder": _alpha(fg, "20"),

        # Editor group header
        "editorGroup.background": bg,
        "editorGroupHeader.background": bg,
        "editorGroupHeader.tabsBackground": bg,
        "editorGroupHeader.tabsBorder": _alpha(fg, "10"),
        "editorGroupHeader.noTabsBackground": bg,
        "editorGroupHeader.dropBackground": _alpha(sel, "30"),
        "editorGroup.emptyBackground": bg,

        # Debug toolbar (the arrows delante/detrás)
        "debugToolBar.background": bg,
        "debugToolBar.border": _alpha(fg, "20"),

        # Notification buttons (the "aceptar" button)
        "notification.buttonBackground": accent,
        "notification.buttonForeground": activity_badge_fg,
        "notification.buttonHoverBackground": alaja_lighten(accent, 1) if not is_light
                                            else alaja_darken(accent, 1),
        "notification.buttonBorder": accent,
        "notification.centerBorder": _alpha(fg, "20"),
        "notificationToast.background": sidebar_bg,
        "notificationToast.border": _alpha(fg, "30"),
        "notificationToast.foreground": fg,
        "notificationLink.activeForeground": sel,

        # Problems panel icons
        "problemsErrorIcon.foreground": sel,
        "problemsWarningIcon.foreground": tokens["type"],
        "problemsInfoIcon.foreground": tokens["function"],

        # Side bar sections
        "sideBar.dropBackground": _alpha(sel, "30"),

        # List focus indicators
        "list.filterMatchBackground": _alpha(sel, "40"),
        "list.filterMatchBorder": sel,
        "list.invalidItemForeground": sel,
        "list.errorForeground": sel,
        "list.warningForeground": tokens["type"],

        # Panel
        "panel.dropBackground": _alpha(sel, "30"),

        # Inputs
        "inputOption.hoverBorder": _alpha(accent, "50"),

        # Status bar debug / nofolder
        "statusBar.debuggingForeground": activity_badge_fg,

        # Window borders
        "window.activeBorder": accent,
        "window.inactiveBorder": _alpha(fg, "20"),

        # Find match borders
        "editor.findMatchHighlightBorder": _alpha(sel, "50"),

        # Chart specific shades
        "charts.red": sel,
        "charts.blue": tokens["function"],
        "charts.green": tokens["function"],
        "charts.yellow": tokens["type"],
        "charts.orange": tokens["type"],
        "charts.purple": accent,
        "charts.lines": _alpha(fg, "30"),

        # Peek view borders
        "peekViewTitle.border": _alpha(fg, "20"),

        # icon.foreground is the colour used by VSCode for any icons
        # that respect the colour theme. The activity-bar icons do
        # honour it on recent VSCode versions, so we set it to accent
        # as well (alongside activityBar.foreground). This belt-and-
        # suspenders covers any icon the user might expect to be
        # themed but that bypasses activityBar.foreground.
        "icon.foreground": accent,
    }
    colors.update(extra_colors)

    # ---- tokenColors ----
    # Helper: build a settings dict, omitting fontStyle when None so
    # the JSON stays clean and VSCode applies no style override.
    def _s(role: str, color: str, *, force_style: str | None = None) -> dict:
        style = force_style if force_style is not None else _ts(role, is_light)
        out: dict = {"foreground": color}
        if style:
            out["fontStyle"] = style
        return out

    token_colors = [
        # Comments
        {"scope": "comment", "settings": _s("comment", tokens["comment"])},
        {"scope": "comment.line", "settings": _s("comment.line", tokens["comment"])},
        {"scope": "comment.block", "settings": _s("comment.block", tokens["comment"])},
        {"scope": "comment.documentation",
         "settings": _s("comment.documentation", tokens["comment"])},

        # Strings
        {"scope": "string", "settings": _s("string", tokens["string"])},
        {"scope": "string.quoted", "settings": _s("string.quoted", tokens["string"])},
        {"scope": "string.template",
         "settings": _s("string.template", tokens["string"])},
        {"scope": "string.interpolated",
         "settings": _s("string.interpolated", tokens["string"])},
        {"scope": "string.regexp",
         "settings": _s("string.regexp", tokens["string_regex"])},

        # Constants
        {"scope": "constant.numeric",
         "settings": _s("constant.numeric", tokens["number"])},
        {"scope": "constant.character",
         "settings": _s("constant.character", tokens["number"])},
        {"scope": "constant.character.escape",
         "settings": _s("constant.character.escape", tokens["constant_char_escape"])},
        {"scope": "constant.language",
         "settings": _s("constant.language", tokens["constant_lang"])},
        {"scope": "variable.other.constant",
         "settings": _s("variable.other.constant", tokens["number"])},

        # Keywords / storage
        {"scope": "keyword", "settings": _s("keyword", tokens["keyword"])},
        {"scope": "keyword.control",
         "settings": _s("keyword.control", tokens["keyword"])},
        {"scope": "keyword.operator",
         "settings": _s("keyword.operator", tokens["keyword"])},
        {"scope": "keyword.other",
         "settings": _s("keyword.other", tokens["keyword"])},
        {"scope": "storage", "settings": _s("storage", tokens["keyword"])},
        {"scope": "storage.modifier",
         "settings": _s("storage.modifier", tokens["keyword"])},
        {"scope": "storage.type",
         "settings": _s("storage.type", tokens["type"])},

        # Entities
        {"scope": "entity.name.function",
         "settings": _s("entity.name.function", tokens["function"])},
        {"scope": "entity.name.function.member",
         "settings": _s("entity.name.function.member", tokens["function"])},
        {"scope": "entity.name.class",
         "settings": _s("entity.name.class", tokens["class"])},
        {"scope": "entity.name.struct",
         "settings": _s("entity.name.struct", tokens["class"])},
        {"scope": "entity.name.type",
         "settings": _s("entity.name.type", tokens["type"])},
        {"scope": "entity.name.tag",
         "settings": _s("entity.name.tag", tokens["keyword"])},
        {"scope": "entity.other.attribute-name",
         "settings": _s("entity.other.attribute-name", tokens["parameter"])},

        # Support
        {"scope": "support.function",
         "settings": _s("support.function", tokens["function"])},
        {"scope": "support.class",
         "settings": _s("support.class", tokens["class"])},
        {"scope": "support.type",
         "settings": _s("support.type", tokens["type"])},
        {"scope": "support.constant",
         "settings": _s("support.constant", tokens["type"])},
        {"scope": "support.variable",
         "settings": _s("support.variable", tokens["type"])},

        # Variables
        {"scope": "variable", "settings": _s("variable", fg)},
        {"scope": "variable.other.readwrite",
         "settings": _s("variable.other.readwrite", fg)},
        {"scope": "variable.parameter",
         "settings": _s("variable.parameter", tokens["parameter"])},
        {"scope": "variable.other.property",
         "settings": _s("variable.other.property", tokens["property"])},

        # Punctuation
        {"scope": "punctuation", "settings": _s("punctuation", _alpha(fg, "B0"))},
        {"scope": "punctuation.definition.string",
         "settings": _s("punctuation.definition.string", tokens["string"])},
        {"scope": "punctuation.definition.comment",
         "settings": _s("punctuation.definition.comment", tokens["comment"])},
        {"scope": "punctuation.definition.tag",
         "settings": _s("punctuation.definition.tag", tokens["keyword"])},
        {"scope": "punctuation.separator",
         "settings": _s("punctuation.separator", _alpha(fg, "B0"))},

        # NOTE: `invalid` / `invalid.deprecated` / `invalid.illegal`
        # are intentionally NOT overridden. VSCode's default rendering
        # for these scopes is the squiggly red underline that signals
        # a syntax error. Painting it with the theme accent (especially
        # in bold + underline) was creating false-positive "everything
        # is an error" appearances and also stealing the canonical red
        # error marker from real issues. We let VSCode handle these.

        # Markup
        {"scope": "markup.heading",
         "settings": _s("markup.heading", tokens["keyword"])},
        {"scope": "markup.bold",
         "settings": _s("markup.bold", fg)},
        {"scope": "markup.italic",
         "settings": _s("markup.italic", fg)},
        {"scope": "markup.underline",
         "settings": _s("markup.underline", fg)},
        {"scope": "markup.inline.raw",
         "settings": _s("markup.inline.raw", tokens["number"])},
        {"scope": "markup.list.unnumbered",
         "settings": _s("markup.list.unnumbered", tokens["parameter"])},
        {"scope": "markup.list.numbered",
         "settings": _s("markup.list.numbered", tokens["parameter"])},
        {"scope": "markup.quote",
         "settings": _s("markup.quote", tokens["comment"])},
        {"scope": "markup.deleted",
         "settings": _s("markup.deleted", tokens["keyword"])},
        {"scope": "markup.inserted",
         "settings": _s("markup.inserted", tokens["function"])},
        {"scope": "markup.changed",
         "settings": _s("markup.changed", tokens["type"])},

        # Meta / diff
        {"scope": "meta.diff",
         "settings": _s("meta.diff", tokens["parameter"])},
        {"scope": "meta.diff.header",
         "settings": _s("meta.diff.header", tokens["keyword"])},
        {"scope": "meta.range",
         "settings": _s("meta.range", tokens["type"])},

        # Emphasis
        {"scope": "emphasis.strong",
         "settings": _s("emphasis.strong", fg)},
        {"scope": "emphasis.italic",
         "settings": _s("emphasis.italic", fg)},
        {"scope": "entity.name.link",
         "settings": _s("entity.name.link", tokens["string"])},
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
    if not meta or meta.get("schema_version") not in (3, 4):
        raise ValueError("Themixir.json missing _meta.schema_version in {3, 4}")

    palettes: dict[str, dict] = raw  # type: ignore

    def _build(color_variant: tuple[str, str]) -> dict:
        color_name, variant = color_variant
        base = palettes[color_name]
        return build_theme(color_name, variant, base)

    pairs = [(c, v) for c in palettes for v in VARIANTS]
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(_build, pairs))


def write_themes(themes: list[dict]) -> list[dict]:
    themes_dir = ROOT / "themes"
    themes_dir.mkdir(exist_ok=True)
    for f in themes_dir.glob("*.json"):
        f.unlink()

    manifest: list[dict] = []
    for theme in themes:
        name = theme["name"]
        stripped = name.replace("Themixir ", "")
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