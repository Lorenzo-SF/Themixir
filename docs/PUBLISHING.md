# Publishing Themixir to the VS Code Marketplace

This guide covers the end-to-end workflow to package, version, and publish the
Themixir theme extension to the Visual Studio Code Marketplace, Open VSX, and
compatible IDE (s (Cursor, Antigravity, Windsurf, etc.).

## Prerequisites

### 1. Microsoft / Azure DevOps account

You need an Azure DevOps organisation to publish extensions on the VS Code
Marketplace. Steps:

1. Create a free Microsoft account if you don't have one.
2. Sign in to <https://dev.azure.com> and create an organisation
   (any name works; e.g. `your-name`).
3. The Marketplace uses your Azure DevOps identity as the publisher. The
   publisher id (`publisher` in `package.json`) must match the organisation
   name you created in lower-case.

### 2. Personal Access Token (PAT)

1. Go to <https://dev.azure.com/<your-org>/_usersSettings/tokens>.
2. Create a new token with:
   - **Organisation**: All accessible organisations
   - **Scopes**: Custom → **Marketplace → Manage**
3. Save the token securely (you'll only see it once).

### 3. Install `vsce`

`vsce` is the official VS Code extension packaging tool.

```bash
npm install -g @vscode/vsce
# verify
vsce --version
```

## One-time setup

### Create the publisher (only if you have never published before)

```bash
vsce create-publisher <your-publisher-id>
```

The publisher id is case-sensitive and must match `publisher` in `package.json`.
For Themixir the publisher is `Lorenzo-SF`.

### Login

```bash
vsce login <your-publisher-id>
```

You'll be prompted for the PAT from step 2 above. The token is cached in
`~/.vsce` (plain text on Linux/macOS, encrypted on Windows).

To verify:

```bash
vsce ls-publishers
```

You should see `Lorenzo-SF` in the list.

## Development workflow

1. **Edit `Themixir.json`** if you want to change a palette.
2. **Run the generator** to produce all 50 theme JSONs and update
   `package.json`:

   ```bash
   python3 generate_themes.py
   ```

3. **Verify locally** in VS Code / Cursor / Antigravity:

   - Open the `Themixir` folder as a workspace.
   - Press `F5` (Run → Start Debugging). A new window opens with the
     extension loaded.
   - Use `Cmd+K Cmd+T` (macOS) / `Ctrl+K Ctrl+T` (Linux/Windows) and pick any
     "Themixir …" theme. Validate:
     - Editor is readable in long sessions.
     - Token colours are distinguishable (keywords vs strings vs functions).
     - Terminal ANSI 16 colours match the palette.
     - Git decorations render with the expected hues.
     - Bracket match, find match, peek view, diff editor all look right.
   - Inspect widgets: settings UI, command palette, notifications, suggest
     widget, hover widget, terminal.

4. **Commit** your changes. See "Versioning policy" below.

## Release workflow

Use the included `scripts/release.sh` to cut a new version:

```bash
./scripts/release.sh patch     # 1.0.2 → 1.0.3  (tweaks)
./scripts/release.sh minor     # 1.0.2 → 1.1.0  (new themes / colors)
./scripts/release.sh major     # 1.0.2 → 2.0.0  (palette overhaul)
```

The script:

1. Reads the current `version` from `package.json`.
2. Bumps it (patch / minor / major).
3. Regenerates the themes (`python3 generate_themes.py`).
4. Commits with a conventional commit message (`chore(release): vX.Y.Z`).
5. Tags the commit with `vX.Y.Z` (annotated).

It does **not** push or publish. You stay in control of those steps.

After the script runs, publish:

```bash
# 1. Sanity-check the package locally
vsce package
# → produces themixir-themes-X.Y.Z.vsix

# 2. Publish to the VS Code Marketplace
vsce publish
# (no version arg needed; it reads from package.json)

# 3. Push the release commit + tag to the remote
git push && git push --tags
```

The first publish of a new version takes ~10 minutes to appear on the
Marketplace. Subsequent updates are faster (~2 min).

## Manual alternative (no script)

If you prefer to do it by hand:

```bash
# Bump the version
npm version patch   # or: minor, major
# This also creates the git tag and commit.

# Regenerate themes
python3 generate_themes.py

# Amend the commit so version bump + regenerated files go together
git add -A && git commit --amend --no-edit

# Package & publish
vsce package
vsce publish
```

## Versioning policy

We follow [Semantic Versioning](https://semver.org/):

| Bump   | When                                                         |
|--------|--------------------------------------------------------------|
| major  | Breaking palette overhaul, large token remapping, or rename. Users may need to re-pick themes. |
| minor  | New colours added (e.g. a 6th variant, or a new base hue). New themes appear in the picker. |
| patch  | Tweaks to existing palettes, contrast fixes, added workbench colour coverage. No new themes. |

Pre-1.0 we treat any 0.x bump as patch-equivalent. Once the extension is
1.0.0+, use the table above strictly.

## Common gotchas

| Symptom                                                     | Fix |
|-------------------------------------------------------------|------|
| `Error: Missing publisher name`                             | Set `publisher` in `package.json`. |
| `Error: Personal Access Token is missing or invalid`        | Re-run `vsce login` with a fresh PAT (Azure DevOps tokens expire). |
| `Error: Extension xxx must include a README.md`             | Ensure `README.md` is at the root. |
| `Error: Extension xxx must include a LICENSE`               | Ensure `LICENSE` exists at the root and `license` field in `package.json` points to it. |
| `Error: Icon xxx.png must be PNG, JPEG or GIF, max 128kB`    | Resize/compress `themixir_icon.png`. |
| `Error: File themes/yyy.json is not valid JSON`             | Validate with `python3 -m json.tool themes/yyy.json`. |
| Themes don't show up after publish                          | Wait 5–10 minutes. Hard-refresh the Marketplace page. |
| Token expired                                               | Generate a new PAT and run `vsce login` again. |
| `vsce` not found after `npm install -g`                      | Ensure your npm global bin is on `PATH`. For npm: `npm config get prefix` then add `…/bin` to `PATH`. For yarn: `yarn global dir`. |

## Continuous Integration (optional)

To publish automatically on git tag:

```yaml
# .github/workflows/release.yml (GitHub Actions)
name: Release
on:
  push:
    tags: ['v*']
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm install -g @vscode/vsce
      - run: python3 generate_themes.py
      - run: vsce publish -p ${{ secrets.VSCE_PAT }}
        env:
          VSCE_PAT: ${{ secrets.VSCE_PAT }}
```

Store the PAT as `VSCE_PAT` in your repo's GitHub Secrets. Use the
`Lorenzo-SF` publisher id (already set in `package.json`).

## Smoke test before publishing

Before every release, run this checklist:

- [ ] All 50 themes exist under `themes/`.
- [ ] `python3 -c "import json; json.load(open('package.json'))"` succeeds.
- [ ] `python3 generate_themes.py` is idempotent (running it twice produces
      byte-identical themes).
- [ ] Open VS Code, pick 5 random themes, verify text is readable.
- [ ] Open a Markdown file with strikethrough, bold, italic — verify markup
      scopes render correctly.
- [ ] Open a TypeScript file with HTML/JSX — verify `entity.name.tag` and
      `entity.other.attribute-name` look right.
- [ ] Open a terminal, run `ls --color=always` — verify ANSI 16 matches.
- [ ] Open the Git panel — verify `gitDecoration.*` colours look right.
- [ ] `vsce package` succeeds and produces a `<2 MB` `.vsix`.

That's it. Ship it.