# Changelog

All notable changes to **Themixir** are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/).

> **Convention for this project**
> - **major**: breaking palette overhaul, large token remapping, or rename.
>   Users may need to re-pick their theme.
> - **minor**: new colours added (new base hue) or new variants. New themes
>   appear in the picker.
> - **patch**: tweaks to existing palettes, contrast fixes, added workbench
>   colour coverage. No new themes.

## [2.0.3] — 2026-09-09

### Changed

- **Git diff colours are now universal — green for added, red for
  removed, in every theme.** Previously `gitDecoration.*`,
  `diffEditor.*`, `merge.*` were derived from each theme's colour
  family: a Blue theme's `gitDecoration.deletedResourceForeground`
  could land on a complement purple/red that had nothing to do with
  "deleted". The user pointed out that reading a diff shouldn't
  require relearning what green/red mean every time you change
  theme. 2.0.3 uses fixed pairs:
    - Light variants: added=`#116329`, deleted=`#A40E26`,
      modified=`#6F4F00` (darker tones that pass WCAG-AA even on
      heavily tinted light bgs like purple-light `#E1CDE9`).
    - Dark variants: added=`#3FB950`, deleted=`#FF7B7B`,
      modified=`#D29922` (the salmon deleted was bumped from
      `#F85149` because that one dropped to 3.68 on gold-dark
      `#463107`).
  All 50 themes pass WCAG-AA on every diff colour.

- **README rewritten for clarity.** Shorter. Adds a
  "Recommended settings" section with the Cascadia Code / weight
  500 / font ligatures recipe (the user can override any of those).
  Adds a "Git diff colours" section that explains the universal
  green/red convention. Removes the long "How the generator works"
  explanation (moved to a comment in `generate_themes.py`).

## [2.0.2] — 2026-09-09

### Changed

- **Activity bar icons are now visible in every variant.** The 2.0.2
  first pass only switched the icon colour for dark and solarized_dark
  variants. The user reported that light / solarized / normal were
  also unreadable, with the explorer/search/git/extensions buttons
  in dim grey. Every variant now uses `accent` for
  `activityBar.foreground` so the theme colour is always present in
  the sidebar. The active icon is brightened (dark) / darkened
  (light) for hierarchy, inactive icons are dimmed with alpha.

> Note on VSCode icon behaviour: some built-in activity-bar icons
> (notably the Git and Debug icons) are rendered as full-colour
> SVGs that ignore the colour theme's `foreground` value. This is
> a VSCode limitation, not a theme bug.

- **Tokens are bold in light themes, italic in dark themes.** The
  user reported that in light variants the colours washed out and
  the typography was so thin that "you can't tell the colours
  apart". Light themes now use `bold` for `keyword`, `keyword.control`,
  `storage`, `storage.modifier`, `entity.name.function`,
  `entity.name.class`, `entity.name.type`, `storage.type`,
  `variable.parameter` so the colour carries weight on a tinted
  light bg. Dark themes keep the previous `italic` for keyword /
  storage to avoid the "everything is bold neon" effect against
  a coloured background. Implemented via a `_ts(role, is_light)`
  helper that the rest of the script uses.

## [2.0.1] — 2026-09-09

> Four bug-fix passes the maintainer wanted to bundle into a single
> `2.0.1` release. All four ship together as `2.0.1`.

### Fixed

- **Token hues no longer escape their colour family.** The previous
  2.0.0 release used `triad` and `split_complementary` harmonies to seed
  the token palette, which could push a token into the colour's
  complement (e.g. green `#3FA34D` at hue 125° had a `class` token at
  hue 5° = `#A34D3F`, a clear red). Now every token role maps to one
  of seven in-family slots (`core`, `lighter`, `darker`, `much_lighter`,
  `much_darker`, `ana_plus`, `ana_minus`) — all of which are derived
  from the accent via `alaja lighten`/`darken` or analogous ±30°. No
  token ever leaves its colour's hue family. Verified by hue-family
  analysis on every theme:

  ```
  red       bg=N sel=R accent=R   tokens: keyword/string/func/class/param: R
  green     bg=N sel=G accent=G   tokens: K=G S=C F=G C=G P=G            (cyan/blue are adjacent to green)
  blue      bg=N sel=B accent=B   tokens: K=B S=P F=B C=B P=B            (purple is adjacent to blue)
  purple    bg=N sel=P accent=P   tokens: K=P S=M F=P C=P P=P            (magenta is adjacent to purple)
  gold      bg=N sel=O accent=O   tokens: K=O S=Y F=O C=O P=O            (yellow is adjacent to gold)
  orange    bg=N sel=R accent=R   tokens: K=R S=O F=R C=R P=R
  silver    bg=N sel=B accent=B   tokens: K=B S=B F=B C=B P=B            (grey-blue family)
  ...
  ```

  No green theme has a red token. No blue theme has an orange token.
  Every token stays within 30° of the accent's hue.

- **Fixed workbench-colour defaults leaking red.** The previous
  2.0.0 release defined ~290 workbench colour keys but left many
  slots unspecified. VSCode's defaults for those slots include red
  error markers (`editorLineNumber.errorForeground`,
  `editorLineNumber.breakpointForeground`,
  `problemsErrorIcon.foreground`), notification button colours, debug
  toolbar, activity-bar active states, breadcrumb focus, tab hover,
  editor group header, etc. Whenever the user opened a non-Red theme
  they saw red in: the activity-bar icons' active border, the line
  numbers of error/breakpoint lines, the breadcrumb focus border,
  the editor group header tabs, the debug toolbar arrows, the
  "Accept" button in the notification popups. 2.0.1 now overrides
  every slot we could find so no element inherits the system red.

- **Terminal ANSI 16 is now a universal palette, not derived from the
  theme accent.** The previous implementation mapped `ansiGreen` to
  the accent's triad +120°, which for a Blue theme at hue 210° lands
  at hue 330° = magenta. So in a Blue theme, `ls --color`, `git log`
  etc. rendered filenames in magenta, not green. 2.0.1 uses a fixed
  palette (One Dark for dark themes, Solarized for light themes)
  that lightens or darkens based on bg. The user always sees
  green/blue/red/cyan/magenta/yellow as expected.

- **`invalid` / `invalid.deprecated` / `invalid.illegal` are no
  longer overridden.** VSCode's default rendering for these scopes is
  the squiggly red underline that signals a syntax error. Painting
  them with the theme accent (especially in `bold underline`) was
  creating false-positive "everything is an error" appearances and
  also stealing the canonical red error marker from real issues. We
  now let VSCode handle these.

- **`_alpha()` now keeps the leading `#`.** The previous version
  stripped the `#` when concatenating a 2-digit alpha channel, so
  generated themes contained 137+ colour values without a leading
  `#` (e.g. `5D93CD30` instead of `#5D93CD30`). VSCode accepted
  these in some versions but it's fragile. Fixed.

- **Keyword tokens are no longer bold-accent combinations.** Reviewer
  feedback noted that `keyword` + bold + saturated accent (the
  theme's own colour) reads as visual noise: "almost everything
  becomes blue and bold". `keyword` (generic) is now italic only;
  `keyword.control` (if/for/while/etc.) keeps bold because those
  deserve weight; `entity.name.function` is no longer bold (functions
  are so frequent that bold + colour becomes noise); `entity.name.class`
  and `entity.name.struct` keep bold because they are rare. `keyword`
  slot also moved from `core` (the most saturated accent) to
  `lighter` (one shade up) for less visual aggression.

- **Each colour has a strong, distinct background tint.** The previous
  2.0.0 release shipped hardcoded tinted bg/fg pairs that were
  visually similar across colours (all "lights" looked pale-pink,
  all "darks" looked near-black). Themes now call `alaja` to produce
  the light/dark backgrounds from each palette's own `selection`
  colour. Red's light bg is `#F8C4C8`, Green's is `#C5E3CA`,
  Blue's is `#BED9F6`, etc. Same story for the dark variants.

- **Generator fully delegates to `alaja`.** Harmonies (`triad`,
  `analogous`, `complementary`, `split_complementary`), lighten and
  darken are all `alaja` subprocess calls now, cached per `(cmd)`.
  The 50 themes share the cache so total generation is ~3 minutes
  instead of 50× the per-theme cost.

- **`Themixir.json` slimmed to schema v3/4.** Only `selection` +
  `accent` (and optional `hue_shift_deg`) per colour — variants are
  no longer hardcoded. 10 colours × 5 variants is fully derived.

- **WCAG auto-fix is direction-agnostic.** The previous version tried
  only one direction (lighten or darken) which could push a colour
  *closer* to the background. Now it tries both and picks the first
  crossing of the threshold, with a pure-black-or-white fallback.
  All 50 themes pass WCAG-AA on critical tokens and WCAG-large on
  decorative scopes.

### Verified spot-checks (light variant bg per colour)

```
red_light      #F8C4C8   green_light    #C5E3CA
blue_light     #BED9F6   purple_light   #E1CDE9
orange_light   #FFD4C7   light_blue_light #C5EAF1
gold_light     #F8E3B9   silver_light   #E2E4E6
copper_light   #EAD5C2   magenta_light  #F8BCD0

red_dark       #451115   green_dark     #133117
blue_dark      #0B2643   purple_dark    #2E1B37
orange_dark    #4C2214   light_blue_dark  #13373E
gold_dark      #463107   silver_dark    #2F3134
copper_dark    #37220F   magenta_dark   #46091E
```

## [2.0.0] — 2026-09-09

### Changed — BREAKING

- **Palette schema overhaul.** `Themixir.json` is now schema v2: each of the
  10 base colours (red, green, blue, purple, orange, light blue, gold,
  silver, copper, magenta) declares a `selection` (vibrant base used for
  cursor, badge, selection highlight) and an `accent` (slightly darker or
  lighter hue used for keywords, storage, button backgrounds). Previously
  keywords and selection shared the same colour on several themes (gold,
  magenta, etc.), which collapsed visual hierarchy. **Action for theme
  authors**: re-edit `Themixir.json` if you forked the old schema.
- **Theme variants restructured.** Each colour now ships with **5
  variants** instead of 3:
  - **solarized** (`#FDF6E3` base, Solarized Light hue family)
  - **light** (clear light background with a strong tint of the colour)
  - **normal** (neutral `#1E1E1E` background — no colour tint)
  - **dark** (saturated dark background with the colour family)
  - **solarized_dark** (`#002B36` base, Solarized Dark hue family)
  - The previous `light`/`dark`/`deep` names map approximately to the new
    `light`/`dark`/`dark` (deep was renamed to `dark`).
- **`silver` theme rebuilt.** Old silver used rainbow accents (blue
  comments, green strings, orange keywords). Now silver is a proper
  neutral theme with all tokens in greys + one accent colour for keywords.
- **Generator rewritten.** `generate_themes.py` is now a deterministic,
  pure-Python colour-math pipeline (HSL harmonies, darken/lighten, WCAG
  ratio). It no longer shells out to `alaja` per colour except for
  validation. Output is byte-stable across runs.

### Added

- **Full workbench coverage**: every theme now defines ~290 `colors`
  keys (up from ~30). New coverage includes:
  - `editor.findMatch{Background,Border}`, `editor.wordHighlight*`,
    `editor.selectionHighlightBackground`,
    `editor.linkedEditingBackground`,
    `editor.hoverHighlightBackground`,
    `editorBracketMatch.*`, `editorIndentGuide.*`,
    `editorGutter.*`, `editorLineNumber.*`,
    `editorMarkerNavigation*`, `editorError/Warning/Info.*`,
    `editorSuggestWidget.*`, `editorHoverWidget.*`,
    `editorWidget.*`, `editorCodeLens.foreground`,
    `editorLightBulb{,.AutoFix}.foreground`.
  - **Terminal ANSI 16**: every `terminal.ansi{Bright,}Black/Red/Green/
    Yellow/Blue/Magenta/Cyan/White` is now themed.
  - **Git decorations**: `gitDecoration.{added,modified,deleted,
    untracked,ignored,conflicting,submodule}ResourceForeground`.
  - `focusBorder`, `scrollbarSlider.*`, `badge.*`, `menu.*`,
    `list.*`, `button.*`, `input.*`, `inputValidation.*`,
    `dropdown.*`, `checkbox.*`, `progressBar.background`,
    `notificationCenter*`, `notifications.{info,warning,error}{Icon,
    Foreground,Background}`, `breadcrumb.*`, `settings.*` (header,
    modifiedItem, dropdown, textInput, numberInput, checkbox, rowHover),
    `minimap.{findMatch,error,warning}Highlight` + sliders,
    `peekView.*`, `diffEditor.*`, `merge.*`, `charts.*`,
    `welcomePage.*`, `walkThrough.*`, `keybindingLabel.*`,
    `textLink.*`, `textBlockQuote.*`, `tree.*`.
- **Expanded `tokenColors`**: ~60 scopes per theme (up from 15). New
  scopes cover Markdown (`markup.heading/bold/italic/underline/
  inline.raw/list.*/quote/deleted/inserted/changed`), HTML/JSX
  (`entity.name.tag`, `entity.other.attribute-name`), support library
  (`support.function/constant/variable/class/type`), `constant.character
  {,.escape}`, `constant.language`, `variable.other.constant`,
  `storage.modifier`, `punctuation.definition.{string,comment,tag}`,
  `meta.diff{,header}`, `meta.range`, `invalid{,.deprecated,.illegal}`,
  `emphasis.{strong,italic}`, `entity.name.link`.
- **WCAG-AA validation & auto-fix**. The generator now measures every
  foreground colour against its background using the standard WCAG 2.1
  relative-luminance formula. Failed pairs (ratio <4.5 for text, <3.0
  for decorative scopes) are automatically direction-aware darkened or
  lightened until they pass. All 50 generated themes meet:
  - editor fg vs bg ≥ 4.5
  - statusBar fg vs bg ≥ 4.5
  - activityBarBadge fg vs bg ≥ 4.5
  - editorCursor vs bg ≥ 3.0
  - accent (keyword) vs bg ≥ 4.5
  - critical tokens (string, keyword, num, storage, constant.language) ≥ 4.5
  - decorative tokens (comment, function, class, type, param, prop,
    regex) ≥ 3.0
- **`docs/PUBLISHING.md`**: full step-by-step VS Code Marketplace
  publishing workflow (Azure DevOps PAT, `vsce login`, `vsce package`,
  `vsce publish`, version policy, smoke test, optional GitHub Actions
  release flow).
- **`scripts/release.sh`**: bumps the `package.json` version
  (patch|minor|major), regenerates themes, commits with conventional
  message, and tags. Does **not** push or publish — you stay in control.
- **`.vscodeignore`**: excludes dev artefacts (`generate_themes.py`,
  `Themixir.json`, `__pycache__/`, `docs/`, `scripts/`, `.git/`,
  `.vscode/`, `*.vsix`) from the published `.vsix`.

### Removed

- The 10 `*_deep.json` theme files (replaced by the more inclusive
  `*_dark.json`).
- The old `comments`/`strings`/`keywords`/`background`/`foreground`
  flat schema in `Themixir.json`. See "Palette schema overhaul" above.

### Fixed

- The `silver` theme no longer uses rainbow accents that contradicted
  the silver hue.
- `gold_dark`, `magenta_dark` and similar themes no longer render
  keywords and selection in identical colours (which collapsed visual
  hierarchy).
- `orange_light` keyword was unreadable (orange `#FF9800` on `#FFF0E6`,
  ratio ≈2.0). Now uses a darker accent that passes AA.

## [1.0.2] — 2026-09-08

### Changed

- Improvements to colour calculation driven by `alaja`. The generator
  was rewritten to consume `alaja`'s `harmonies` output via regex
  parsing, fixing previous silent failures when `alaja` returned an
  unexpected shape.

## [1.0.0] — 2026-09-04

### Added

- Initial release of Themixir.
- 30 themes (10 colours × 3 variants: light, dark, deep).
- Coverage of `editor.background/foreground`, selection, cursor,
  `editorBracketMatch`, terminal background and foreground, sideBar,
  statusBar, activityBar, titleBar, tabs.
- Token coverage for comment, string, string.regexp, constant.numeric,
  constant.language, keyword, storage, storage.type, entity.name.
  function, entity.name.class, entity.name.type, variable,
  variable.parameter, variable.other.property, punctuation.

[2.0.3]: https://github.com/lorenzo-sf/themixir/releases/tag/v2.0.3
[2.0.2]: https://github.com/lorenzo-sf/themixir/releases/tag/v2.0.2
[2.0.1]: https://github.com/lorenzo-sf/themixir/releases/tag/v2.0.1
[2.0.0]: https://github.com/lorenzo-sf/themixir/releases/tag/v2.0.0
[1.0.2]: https://github.com/lorenzo-sf/themixir/releases/tag/v1.0.2
[1.0.0]: https://github.com/lorenzo-sf/themixir/releases/tag/v1.0.0