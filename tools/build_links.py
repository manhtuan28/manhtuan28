"""Render the pixel-art link buttons (`link_<name>_<theme>.svg`) sitting between the
neofetch card and the Pac-Man contribution board.

Generates buttons for Facebook, YouTube, and Email in both dark and light themes,
aligning cleanly across `CANVAS_W` (`1018px`).

Usage:
    python tools/build_links.py
"""

from __future__ import annotations

from pathlib import Path

from build_card import ADVANCE, LINE_MID, THEMES
from build_pacman import CANVAS_W, bitmap, loop, mix, sprite_path, validate_smil

ROOT = Path(__file__).resolve().parent.parent

PX = 3
GAP = 14
SLOT_W = CANVAS_W / 3
BUTTON_W = (CANVAS_W - 2 * GAP) / 3
HEIGHT = 20 * PX
LABEL_FONT = 18
ICON_GAP = 12
OUTLINE_MIX = 0.18

assert BUTTON_W % PX == 0, "the button must be a whole number of pixels wide"

FACEBOOK_MARK = """
.########.
##########
#####...##
####..####
####..####
###......#
####..####
####..####
####..####
.###..###.
"""

YOUTUBE_FRAME = """
.########.
#........#
#........#
#........#
#........#
#........#
#........#
.########.
"""

YOUTUBE_PLAY = """
..........
..........
....#.....
....##....
....###...
....##....
....#.....
..........
"""

ENVELOPE = """
##########
##......##
#.#....#.#
#..#..#..#
#...##...#
#........#
#........#
##########
"""

PLAY_BLINK = 1.20
HOP_EVERY = 2.0
RATTLE_EVERY = 2.4


def sprite_svg_path(sprite_art: str) -> str:
    """Convert an ASCII sprite bitmap into an SVG path scaled by `PX`."""
    return sprite_path(bitmap(sprite_art), PX, PX)


def twitch(offsets: list[tuple[int, int]], key_times: list[float], duration: float) -> str:
    """Whole-pixel jump animation (in `PX` units) at discrete normalized `key_times`."""
    values = ";".join(f"{dx * PX},{dy * PX}" for dx, dy in offsets)
    formatted_times = ";".join(f"{val:g}" for val in key_times)
    return (
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="{values}" keyTimes="{formatted_times}" dur="{duration}s" '
        f'calcMode="discrete" repeatCount="indefinite"/>'
    )


def facebook_icon() -> str:
    """Render the Facebook rounded `f` pixel sprite with a subtle vertical hop."""
    hop_anim = twitch([(0, 0), (0, -1), (0, 0)], [0, 0.8, 0.9], HOP_EVERY)
    return f'<g>{hop_anim}<path d="{sprite_svg_path(FACEBOOK_MARK)}"/></g>'


def youtube_icon() -> str:
    """Render the YouTube TV frame with a blinking pixel play triangle."""
    return (
        f'<path d="{sprite_svg_path(YOUTUBE_FRAME)}"/>'
        f'<path d="{sprite_svg_path(YOUTUBE_PLAY)}">{loop("opacity", ["1", "0.35"], PLAY_BLINK)}</path>'
    )


def email_icon() -> str:
    """Render the pixel envelope sprite with a rattle notification animation."""
    rattle_anim = twitch(
        [(0, 0), (-1, 0), (1, 0), (-1, 0), (1, 0), (0, 0)],
        [0, 0.7, 0.74, 0.78, 0.82, 0.86],
        RATTLE_EVERY,
    )
    return f'<g>{rattle_anim}<path d="{sprite_svg_path(ENVELOPE)}"/></g>'


LINKS = (
    ("facebook", "FACEBOOK", "value", facebook_icon),
    ("youtube", "YOUTUBE", "del", youtube_icon),
    ("email", "EMAIL", "key", email_icon),
)


def stepped_rect_path(x_pos: float, y_pos: float, width: float, height: float) -> str:
    """Draw a pixel-stepped rectangle with single-`PX` chamfered corners."""
    return (
        f"M{x_pos + PX:g} {y_pos:g}h{width - 2 * PX:g}v{PX}h{PX}v{height - 2 * PX:g}h{-PX}v{PX}"
        f"h{-(width - 2 * PX):g}v{-PX}h{-PX}v{-(height - 2 * PX):g}h{PX}z"
    )


def build_button(theme_name: str, slot_index: int) -> str:
    """Build the SVG markup for button `slot_index` under `theme_name`."""
    palette = THEMES[theme_name]
    _, label, accent_key, icon_fn = LINKS[slot_index]
    accent_color = palette[accent_key]

    button_x = slot_index * GAP / 3
    icon_w = 10 * PX
    label_w = len(label) * LABEL_FONT * ADVANCE
    content_left = button_x + (BUTTON_W - icon_w - ICON_GAP - label_w) / 2
    vertical_mid = (PX + HEIGHT - 2 * PX) / 2

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" width="{SLOT_W:.3f}px" height="{HEIGHT}px"
     viewBox="0 0 {SLOT_W:.3f} {HEIGHT}" font-family="ConsolasFallback,Consolas,Menlo,monospace">
<style>
@font-face {{
  src: local('Consolas'), local('Consolas Bold');
  font-family: 'ConsolasFallback';
  font-display: swap;
  size-adjust: 109%;
}}
text {{white-space: pre;}}
.px {{shape-rendering: crispEdges;}}
</style>
<g class="px">
<path d="{stepped_rect_path(button_x, 0, BUTTON_W, HEIGHT)}" fill="{mix(palette['bg'], palette['fg'], OUTLINE_MIX)}"/>
<path d="{stepped_rect_path(button_x + PX, PX, BUTTON_W - 2 * PX, HEIGHT - 2 * PX)}" fill="{palette['bg']}"/>
<rect x="{button_x + 2 * PX:g}" y="{HEIGHT - 2 * PX}" width="{BUTTON_W - 4 * PX:g}" height="{PX}" fill="{accent_color}"/>
<g fill="{accent_color}" transform="translate({content_left + icon_w / 2:.2f},{vertical_mid:g})">{icon_fn()}</g>
</g>
<text x="{content_left + icon_w + ICON_GAP:.2f}" y="{vertical_mid + LINE_MID * LABEL_FONT:.2f}" font-size="{LABEL_FONT}px" fill="{palette['fg']}">{label}</text>
</svg>
"""


def main() -> None:
    """Regenerate all dark and light link button SVGs in the repository root."""
    print(f"row      : {CANVAS_W}px = 3 x {BUTTON_W:g}px buttons + 2 x {GAP}px gaps")
    for theme_name in THEMES:
        for slot_index, (button_name, *_) in enumerate(LINKS):
            svg_markup = build_button(theme_name, slot_index)
            checked = validate_smil(svg_markup)
            out_path = ROOT / f"link_{button_name}_{theme_name}.svg"
            out_path.write_text(svg_markup, encoding="utf-8")
            print(f"wrote {out_path.name} ({out_path.stat().st_size:,} bytes, {checked} animations validated)")


if __name__ == "__main__":
    main()
