#!/usr/bin/env bash
# scripts/release.sh — Bump version, regenerate themes, commit, tag.
#
# Usage: ./scripts/release.sh [patch|minor|major]  (default: patch)
#
# Does NOT push or publish. After this script runs:
#   1. Review the commit + tag with `git log` and `git tag`.
#   2. Push with `git push && git push --tags`.
#   3. Publish with `vsce publish` (or `vsce package` first for a dry-run).
#
# Requirements: python3 on PATH; jq on PATH; git working tree clean.

set -euo pipefail

# ------------------------------------------------------------ args ----
BUMP="${1:-patch}"
case "$BUMP" in
  patch|minor|major) ;;
  *)
    echo "Usage: $0 [patch|minor|major]" >&2
    exit 64
    ;;
esac

# ------------------------------------------------------------ preflight ----
if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found on PATH" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq not found on PATH. Install with: apt install jq / brew install jq" >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "Error: working tree is dirty. Commit or stash changes first." >&2
  git status --short >&2
  exit 1
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# ------------------------------------------------------------ bump version ----
CURRENT_VERSION="$(jq -r '.version' package.json)"
echo "Current version: $CURRENT_VERSION"

# Use python to compute next semver (more portable than `npm version`)
NEXT_VERSION="$(python3 -c "
v = '$CURRENT_VERSION'.split('.')
bump = '$BUMP'
parts = [int(p) for p in v]
if bump == 'major':
    parts = [parts[0] + 1, 0, 0]
elif bump == 'minor':
    parts = [parts[0], parts[1] + 1, 0]
else:  # patch
    parts = [parts[0], parts[1], parts[2] + 1]
print('.'.join(str(p) for p in parts))
")"

echo "New version:     $NEXT_VERSION"

# Update package.json in place
python3 -c "
import json, sys
p = json.load(open('package.json', 'r'))
p['version'] = '$NEXT_VERSION'
json.dump(p, open('package.json', 'w'), indent=2)
"

# ------------------------------------------------------------ regenerate themes ----
echo "Regenerating themes..."
python3 generate_themes.py

# ------------------------------------------------------------ commit + tag ----
echo "Committing release..."
git add package.json themes/
git commit -m "chore(release): v$NEXT_VERSION"
git tag -a "v$NEXT_VERSION" -m "Release v$NEXT_VERSION"

echo
echo "Done. Next steps:"
echo "  1. Review:   git log -1 && git tag --list 'v$NEXT_VERSION'"
echo "  2. Push:     git push && git push --tags"
echo "  3. Sanity:   vsce package    (builds .vsix locally)"
echo "  4. Publish:  vsce publish    (pushes to VS Code Marketplace)"
echo
echo "If 'vsce' is not on PATH, install it with: npm install -g @vscode/vsce"