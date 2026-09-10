# Themixir! Elixir Themes for VS Code (and Cursor, and Antigravity, and all the folks)

A collection of **50 vibrant themes** for your favourite IDE, built on
custom palettes with WCAG-AA contrast, full workbench coverage (terminal
ANSI 16, git decorations, bracket/find/hover widgets, etc.), and
syntax highlighting tuned for readability.

Powered by [Alaja](https://github.com/lorenzo-sf/alaja) for colour
harmonies and validated against WCAG 2.1 contrast ratios.

## Features

- **10 Core Colours**: Red, Green, Blue, Purple, Orange, Light Blue, Gold,
  Silver, Copper, Magenta.
- **5 Variants per Colour**:
  - **Solarized** — crisp light Solarized-style base, low saturation.
  - **Light** — clear light backgrounds with a strong tint of the colour.
  - **Normal** — neutral dark background (`#1E1E1E`), perfect for users who
    want a dark theme that doesn't tint the whole workbench.
  - **Dark** — saturated dark background with the colour family.
  - **Solarized Dark** — Solarized Dark-style base (`#002B36`).
- **Full workbench coverage**: ~330 colour keys per theme — editor, terminal
  ANSI 16, git decorations, bracket match, find match, peek view, diff
  editor, merge, notifications, widgets, settings, breadcrumb, debug
  toolbar, notification buttons, etc.
- **In-family token palette**: every token colour stays inside the colour's
  own hue family. A green theme never has red/magenta tokens; a blue theme
  never has orange tokens. Tokens are derived from the accent via `alaja`
  lighten/darken and analogous ±30° — no complements, no triad.
- **WCAG-AA contrast**: editor foreground vs background, keyword vs
  background, status bar, activity badge, and other UI components all pass
  ≥4.5. Critical token scopes (strings, keywords, numbers, storage) pass
  ≥4.5; decorative scopes (comments, function names, etc.) pass ≥3.0.
- **Universal terminal ANSI 16**: `ansiGreen` is always green, `ansiBlue`
  always blue, regardless of theme. Light/dark variants use One Dark
  and Solarized palettes respectively.
- **No VSCode red defaults leaking**: error/warning/breakpoint markers
  on line numbers, problems panel, debug toolbar, and notification
  buttons are all themed — none inherit the system red.

## Installation

1. Open **Extensions** in your favourite IDE (`Cmd+Shift+X` / `Ctrl+Shift+X`).
2. Search for **Themixir Themes**.
3. Click **Install**.
4. Select your preferred variant with `Cmd+K Cmd+T` / `Ctrl+K Ctrl+T`.

## Development

### Theme generation

The source of truth is `Themixir.json` (10 palettes × schema v3/v4).
Each palette declares only `selection` (vibrant base) and `accent`
(darker derivative). The generator script `generate_themes.py`
produces all 50 theme JSONs under `themes/` and rewrites the
`contributes.themes` array in `package.json`.

```bash
python3 generate_themes.py
```

The script:

- Derives **bg/fg** for each of the 5 variants via `alaja lighten/darken`
  on the selection colour (the light/dark variants have strong colour
  tints, the solarized/solarized_dark variants use the fixed Solarized
  base palette, and the normal variant is neutral grey).
- Builds an **in-family token palette** of 7 slots (`core`, `lighter`,
  `darker`, `much_lighter`, `much_darker`, `ana_plus`, `ana_minus`)
  all derived from the accent. Every token role maps to one slot.
- Uses a **universal terminal ANSI 16** palette (One Dark / Solarized)
  so `ansiGreen` always means green, never the theme's complement.
- **Auto-fixes WCAG** ratios with both `lighten` and `darken` until
  foreground crosses ≥4.5 (critical tokens) or ≥3.0 (decorative).
- Overrides **~330 workbench colour keys** so no slot inherits VSCode's
  red defaults (line-number errors, problems panel icons, debug
  toolbar, notification buttons, etc.).
- Updates `package.json` only — leaves every other field untouched.

### Packaging and publishing

See [`docs/PUBLISHING.md`](docs/PUBLISHING.md) for the full workflow. TL;DR:

```bash
# One-time
npm install -g @vscode/vsce
vsce login Lorenzo-SF

# Release
./scripts/release.sh patch   # or minor / major
vsce publish

# Optional: pre-build a .vsix to inspect
vsce package
```

### Current version

The latest release is **2.0.1**. See [`CHANGELOG.md`](CHANGELOG.md) for
the full history.

## License

Proprietary - (c) 2026 Lorenzo Sanchez. All rights reserved.
See `LICENSE` file for details.