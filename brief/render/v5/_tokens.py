"""V5 design tokens — Python source of truth.

Mirrors `brief/render/v5/tokens.css` (CSS :root variables). Helpers in
_jsx.py reference these constants directly; templates emit the CSS file
into the page <head>.
"""
from __future__ import annotations

COLORS = {
    "ox":         "#6b1f27",
    "ox_dim":     "#8b3540",
    "ink_1":      "#171310",
    "ink_2":      "#3a322d",
    "ink_3":      "#777",
    "ink_4":      "#aaa",
    "paper_1":    "#faf6ee",
    "paper_2":    "#f1ead9",
    "paper_3":    "#e8e1cd",
    "gold":       "#c89a3f",
    "red":        "#a83a3a",
    "green":      "#3a8f4f",
    "ink_inverse":"#f5f0e8",
}

TYPE = {
    "serif_display": "'Source Serif 4', Georgia, serif",
    "serif_text":    "'Source Serif 4', Georgia, serif",
    "mono":          "'JetBrains Mono', Menlo, monospace",
    "sans":          "'Inter', system-ui, sans-serif",
}

SPACE = {
    "xs": "0.25rem",
    "sm": "0.5rem",
    "md": "1rem",
    "lg": "1.5rem",
    "xl": "2.5rem",
    "2xl": "4rem",
}

KIND_COLOR = {
    "event":  COLORS["ox"],
    "fresh":  COLORS["green"],
    "slow":   COLORS["gold"],
    "anchor": COLORS["ink_1"],
}
