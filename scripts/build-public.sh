#!/usr/bin/env bash
# Assemble the GitHub Pages artifact: the dashboard at /, the API at /api/v1/.
#
# WHY .nojekyll: GitHub Pages otherwise runs the files through Jekyll, which ignores paths starting
# with an underscore and can silently drop files. The marker tells Pages to serve the tree as-is.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

rm -rf public
mkdir -p public/api
cp dashboard/index.html public/index.html
cp -r api/v1 public/api/v1
cp embed/embed.js public/embed.js        # the embeddable chart, served from the site root
cp embed/demo.html public/embed.html     # live demo + copy-paste snippets, at /embed.html
touch public/.nojekyll

echo "[INFO] [Pages] assembled public/ ($(find public -type f | wc -l) files, $(du -sh public | cut -f1))"
echo "[INFO] [Pages] dashboard -> /            API -> /api/v1/   embed -> /embed.js (demo /embed.html)"
