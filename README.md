# Themixir

50 themes for VS Code, Cursor, Antigravity, Windsurf, etc.

10 colours × 5 variants. WCAG-AA contrast. In-family token palette.
Universal green/red for git diffs.

## Quick start

1. Install from the VS Code Marketplace (`Cmd+Shift+X` / `Ctrl+Shift+X`,
   search "Themixir Themes").
2. Pick a theme: `Cmd+K Cmd+T` / `Ctrl+K Ctrl+T` → any "Themixir …"
   variant.
3. Optionally configure fonts (see [Recommended settings](#recommended-settings)).

## Variants

For every colour:

| Variant | Background |
|---|---|
| Solarized | Fixed `#FDF6E3` (Solarized Light base, no theme tint) |
| Light | Tinted from the colour's `selection` (e.g. red → `#F8C4C8`) |
| Normal | Neutral `#1E1E1E` grey |
| Dark | Tinted from the colour's `selection` (e.g. red → `#451115`) |
| Solarized Dark | Fixed `#002B36` (Solarized Dark base) |

10 colours: **red · green · blue · purple · orange · light_blue · gold ·
silver · copper · magenta**.

## Recommended settings

The themes do not pin a font (that's your choice). However, on light
backgrounds coloured tokens can wash out unless the typography has some
weight. The recommended combination is:

```jsonc
// settings.json (User)
{
  "editor.fontFamily": "'Cascadia Code'",
  "editor.fontWeight": "500",
  "editor.fontLigatures": true
}
```

> You can override any of these. If you prefer Fira Code, JetBrains
> Mono, your own handwriting font — just set `editor.fontFamily` to it
> and the theme will keep working.

## Git diff colours

Git diffs (`gitDecoration.*`, `diffEditor.*`, `merge.*`) always show
**green for added / red for removed** — regardless of which colour
theme you picked. This mirrors the universal convention (GitHub,
GitLab, etc.) so your eye doesn't have to relearn what red/green mean
when you switch themes. The tones shift slightly between light and
dark variants (darker on light bgs for AA contrast, brighter on dark)
but the meaning stays the same.

## Accessibility

All 50 themes pass WCAG 2.1:

- `editor.foreground` vs `editor.background` ≥ 4.5 (AA normal text)
- `statusBar`, `activityBarBadge` foreground/background ≥ 4.5
- `accent` (keyword) vs background ≥ 4.5
- Critical token scopes (string, keyword, num, storage, constant) ≥ 4.5
- Decorative scopes (comment, function, class, type, etc.) ≥ 3.0

## Development

### Theme generation

```bash
python3 generate_themes.py
```

Reads `Themixir.json` (10 palettes, schema v3/v4), writes 50 themes
to `themes/`, updates `package.json`. Pure Python (HSL math) for
harmonies + alaja for darken/lighten/contrast validation. Cached
per-(cmd) — full regeneration takes ~3 minutes.

### Adding a colour or variant

Edit `Themixir.json`. Each palette declares `selection` and `accent`.
Re-run the generator. The new theme lands in the file list in
`package.json` automatically.

### Publishing

See [`docs/PUBLISHING.md`](docs/PUBLISHING.md).

## License

Proprietary - (c) 2026 Lorenzo Sanchez. All rights reserved.
See `LICENSE` file for details.