#!/usr/bin/env bash
set -euo pipefail

# Build script: compiles the-brief.html (JSX source) -> index.html (production)
# Steps:
# 1. Copy the-brief.html to index.html
# 2. Extract the <script type="text/babel"> block
# 3. Compile JSX to plain JS via esbuild
# 4. Replace the babel script block with compiled JS in index.html
# 5. Remove the Babel Standalone <script> tag (no longer needed)
# 6. Remove 'unsafe-eval' from CSP (Babel required it, compiled JS doesn't)
# 7. Update service worker cache version with today's date
#
# Chart data comes from Supabase (tb_* tables) now; no API keys to inject.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Building index.html from the-brief.html ==="

# Step 1: Copy source to output
cp the-brief.html index.html

# Step 2: Extract JSX block
# Find the <script type="text/babel"> block and extract its content
python3 -c "
import re, sys
with open('index.html', 'r') as f:
    html = f.read()
m = re.search(r'<script type=\"text/babel\">(.*?)</script>', html, re.DOTALL)
if not m:
    print('ERROR: No <script type=\"text/babel\"> block found', file=sys.stderr)
    sys.exit(1)
with open('_app.jsx', 'w') as f:
    f.write(m.group(1))
print(f'Extracted {len(m.group(1))} chars of JSX')
"

# Step 3: Compile JSX with esbuild
npx esbuild _app.jsx \
  --bundle=false \
  --jsx=transform \
  --jsx-factory=React.createElement \
  --jsx-fragment=React.Fragment \
  --target=es2020 \
  --outfile=_app.js \
  --log-level=warning

echo "Compiled JSX -> JS ($(wc -c < _app.js) bytes)"

# Step 4: Replace babel script block with compiled JS
python3 -c "
import re
with open('index.html', 'r') as f:
    html = f.read()
with open('_app.js', 'r') as f:
    compiled = f.read()
# Find the babel script block boundaries and replace via string slicing (not re.sub)
# to avoid backslash interpretation in the compiled JS
m = re.search(r'<script type=\"text/babel\">', html)
if not m:
    raise SystemExit('ERROR: <script type=\"text/babel\"> not found in index.html')
start = m.start()
end_tag = '</script>'
end = html.index(end_tag, m.end()) + len(end_tag)
html = html[:start] + '<script>' + compiled + end_tag + html[end:]
with open('index.html', 'w') as f:
    f.write(html)
print('Replaced JSX block with compiled JS')
"

# Step 5: Remove Babel Standalone script tag (no longer needed in production)
python3 -c "
import re
with open('index.html', 'r') as f:
    html = f.read()
html = re.sub(r'\s*<script[^>]*babel\.min\.js[^>]*></script>', '', html)
with open('index.html', 'w') as f:
    f.write(html)
print('Removed Babel Standalone script tag')
"

# Step 6: Remove 'unsafe-eval' from CSP (Babel needed it, compiled JS doesn't)
python3 -c "
with open('index.html', 'r') as f:
    html = f.read()
html = html.replace(\"'unsafe-eval' \", '')
with open('index.html', 'w') as f:
    f.write(html)
print('Removed unsafe-eval from CSP')
"

# Step 7: Update service worker cache version
TODAY=$(date +%Y-%m-%d)
sed -i.bak "s/the-brief-v[0-9a-z-]*/the-brief-v2-$TODAY/g" sw.js && rm -f sw.js.bak
echo "Updated SW cache version to the-brief-v2-$TODAY"

# Cleanup temp files
rm -f _app.jsx _app.js

echo "=== Build complete: index.html ($(wc -c < index.html) bytes) ==="
