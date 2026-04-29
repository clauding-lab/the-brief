"""Tokens parity test — every CSS var must have a matching Python token."""
import re
from pathlib import Path

from brief.render.v5 import _tokens

TOKENS_CSS = Path(__file__).parents[3] / "brief" / "render" / "v5" / "tokens.css"


def test_css_var_matches_python_color():
    css = TOKENS_CSS.read_text()
    for key, hex_value in _tokens.COLORS.items():
        # CSS uses hyphens (--ink-1) where Python uses underscores (ink_1)
        css_key = "--" + key.replace("_", "-")
        m = re.search(rf"{re.escape(css_key)}:\s*([^;]+);", css)
        assert m, f"CSS missing var {css_key}"
        assert m.group(1).strip().lower() == hex_value.lower(), \
            f"value mismatch for {key}: py={hex_value} css={m.group(1).strip()}"


def test_css_var_matches_python_type_family():
    css = TOKENS_CSS.read_text()
    py_to_css = {
        "serif_display": "--font-serif-display",
        "serif_text":    "--font-serif-text",
        "mono":          "--font-mono",
        "sans":          "--font-sans",
    }
    for py_key, css_key in py_to_css.items():
        m = re.search(rf"{re.escape(css_key)}:\s*([^;]+);", css)
        assert m, f"CSS missing var {css_key}"
        assert m.group(1).strip() == _tokens.TYPE[py_key], \
            f"value mismatch for {py_key}"


def test_css_var_matches_python_space():
    css = TOKENS_CSS.read_text()
    for key, value in _tokens.SPACE.items():
        css_key = f"--space-{key}"
        m = re.search(rf"{re.escape(css_key)}:\s*([^;]+);", css)
        assert m, f"CSS missing var {css_key}"
        assert m.group(1).strip() == value, \
            f"value mismatch for {key}: py={value} css={m.group(1).strip()}"
