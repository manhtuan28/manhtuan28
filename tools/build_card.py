"""Build the neofetch-style profile card SVGs (`dark_mode.svg` / `light_mode.svg`).

The card is regenerated from scratch on every run: ASCII portraits come from
`assets/ascii-art*.txt` and numbers from `cache/stats.json` (written by
`tools/fetch_stats.py`). Rows are assembled with elastic `fill` runs and
asserted to fit exactly `PANEL_COLS` characters.

Usage:
    python tools/build_card.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASCII_SRC_DARK = ROOT / "assets" / "ascii-art.txt"
ASCII_SRC_LIGHT = ROOT / "assets" / "ascii-art-light.txt"
STATS_SRC = ROOT / "cache" / "stats.json"

BIRTHDATE = dt.date(2004, 2, 28)

# `Consolas` advances `0.55em` per glyph while generic `monospace` advances `0.60em`.
# Declaring `size-adjust: 109%` aligns `Consolas` to `0.5995em` so both render identically.
ADVANCE = 0.5995
ART_COL_WIDTH = 414.0
ART_CELL_ASPECT = 0.54

PANEL_FONT = 16.0
PANEL_LINE = 20.0
PANEL_COLS = 58

MARGIN = 15
GUTTER = 18

LINE_MID = 0.35
LINE_PAD = 0.65

THEMES = {
    "dark": {
        "art_src": ASCII_SRC_DARK,
        "bg": "#161b22",
        "fg": "#c9d1d9",
        "art": "#c9d1d9",
        "key": "#F76E0A",
        "value": "#a5d6ff",
        "add": "#3fb950",
        "del": "#f85149",
        "dots": "#616e7f",
    },
    "light": {
        "art_src": ASCII_SRC_LIGHT,
        "bg": "#ffffff",
        "fg": "#24292f",
        "art": "#24292f",
        "key": "#bc4c00",
        "value": "#0550ae",
        "add": "#1a7f37",
        "del": "#cf222e",
        "dots": "#8c959f",
    },
}

TITLE = "tuan@manhtuan28"

INFO = [
    ("OS", "Windows, Linux, Android"),
    ("Uptime", None),
    ("Host", "Viet Tri, Vietnam"),
    ("Kernel", "Product & Software Engineer"),
    ("IDE", "VS Code, Visual Studio, Android Studio"),
    None,
    ("Languages.Programming", "C#, Python, PHP, JavaScript"),
    ("Languages.Computer", "SQL, PowerShell, HTML, CSS"),
    ("Languages.Real", "Vietnamese, English"),
    None,
    ("Focus.Web", ".NET Core, Laravel, Next.js, React"),
    ("Focus.AI", "OpenCV, ONNX Runtime (DirectML)"),
    ("Focus.System", "Linux, WinServer, FFmpeg, CI/CD"),
    ("Hobbies", "Android RE, Flutter, J2TEAM"),
]

CONTACT = [
    ("Email", "buimanhtuan2k4@gmail.com"),
    ("YouTube", "@Tuancute28"),
    ("Discord", "discord.gg/nugget282"),
]


def art_metrics(cols: int) -> tuple[float, float]:
    """Return `(font_size, line_height)` fitting `cols` characters inside `ART_COL_WIDTH`."""
    font_size = ART_COL_WIDTH / (cols * ADVANCE)
    return font_size, font_size * ADVANCE / ART_CELL_ASPECT


def escape_xml(text_value: str) -> str:
    """Escape XML special characters without altering quotes inside text nodes."""
    return html.escape(text_value, quote=False)


class Row:
    """A neofetch panel row composed of fixed segments and elastic dot/rule fills."""

    def __init__(self) -> None:
        self._segments: list[dict] = []

    def text(self, value: str, css_class: str | None = None, element_id: str | None = None) -> "Row":
        """Append a fixed text segment."""
        self._segments.append({"kind": "text", "value": str(value), "class": css_class, "id": element_id})
        return self

    def key(self, key_label: str) -> "Row":
        """Append a dotted key segment so nested labels like `Languages.Programming` share color."""
        parts = str(key_label).split(".")
        for index, part in enumerate(parts):
            if index:
                self.text(".")
            self.text(part, css_class="key")
        return self

    def value(self, value_text: str, element_id: str | None = None) -> "Row":
        """Append a highlighted value segment."""
        return self.text(value_text, css_class="value", element_id=element_id)

    def fill(self, fill_char: str = ".", css_class: str = "cc", element_id: str | None = None) -> "Row":
        """Append an elastic fill run expanded to match `PANEL_COLS`."""
        self._segments.append({"kind": "fill", "char": fill_char, "class": css_class, "id": element_id})
        return self

    def _fixed_length(self) -> int:
        return sum(len(segment["value"]) for segment in self._segments if segment["kind"] == "text")

    def _fill_widths(self, total_width: int) -> dict[int, int]:
        fill_indices = [idx for idx, segment in enumerate(self._segments) if segment["kind"] == "fill"]
        if not fill_indices:
            return {}
        slack = total_width - self._fixed_length()
        if slack < len(fill_indices):
            raise SystemExit(
                f"row does not fit in {total_width} cols (needs {self._fixed_length() + len(fill_indices)}): "
                f"{''.join(segment.get('value', '~') for segment in self._segments)!r}"
            )
        base_width, remainder = divmod(slack, len(fill_indices))
        return {
            fill_idx: base_width + (1 if position < remainder else 0)
            for position, fill_idx in enumerate(fill_indices)
        }

    def render(self, x_pos: int, y_pos: float, total_width: int) -> str:
        """Render this row as an SVG `<tspan>` string aligned to `total_width` columns."""
        widths = self._fill_widths(total_width)
        rendered_parts: list[str] = []
        rendered_cols = 0
        for index, segment in enumerate(self._segments):
            body = segment["value"] if segment["kind"] == "text" else segment["char"] * widths[index]
            rendered_cols += len(body)
            attrs = ""
            if segment["class"]:
                attrs += f' class="{segment["class"]}"'
            if segment["id"]:
                attrs += f' id="{segment["id"]}"'
            rendered_parts.append(f"<tspan{attrs}>{escape_xml(body)}</tspan>" if attrs else escape_xml(body))
        assert rendered_cols == total_width, f"row rendered {rendered_cols} cols, expected {total_width}"
        return f'<tspan x="{x_pos}" y="{y_pos:g}">{"".join(rendered_parts)}</tspan>'


def info_row(key_label: str, value_text: str, element_id: str | None = None) -> Row:
    """Build a standard `. Key: ..... Value` row."""
    return (
        Row()
        .text(". ", css_class="cc")
        .key(key_label)
        .text(":")
        .text(" ", css_class="cc")
        .fill()
        .text(" ", css_class="cc")
        .value(value_text, element_id)
    )


def rule_row(label: str, bold: bool = False) -> Row:
    """Build a section header divider row padded with em-dashes."""
    row = Row()
    row.text(label, css_class="title" if bold else None)
    row.text(" -").fill("—", css_class=None).text("-")
    return row


def compute_uptime(today: dt.date | None = None) -> str:
    """Calculate elapsed years, months, and days since `BIRTHDATE`."""
    current_date = today or dt.date.today()
    years = current_date.year - BIRTHDATE.year
    months = current_date.month - BIRTHDATE.month
    days = current_date.day - BIRTHDATE.day
    if days < 0:
        months -= 1
        previous_month_end = current_date.replace(day=1) - dt.timedelta(days=1)
        days += previous_month_end.day
    if months < 0:
        years -= 1
        months += 12

    def pluralize(count: int, unit: str) -> str:
        return f"{count} {unit}" + ("" if count == 1 else "s")

    return f"{pluralize(years, 'year')}, {pluralize(months, 'month')}, {pluralize(days, 'day')}"


def load_stats() -> dict[str, str]:
    """Load formatted GitHub stats from `cache/stats.json` or fallback placeholders."""
    stat_keys = ("repos", "contrib", "stars", "commits", "followers", "loc", "added", "deleted")
    placeholders = {stat_key: "--" for stat_key in stat_keys}
    if not STATS_SRC.exists():
        return placeholders
    raw_stats = json.loads(STATS_SRC.read_text(encoding="utf-8"))
    return {
        stat_key: f"{raw_stats[stat_key]:,}" if isinstance(raw_stats.get(stat_key), int) else placeholders[stat_key]
        for stat_key in stat_keys
    }


def load_art(source_path: Path) -> list[str]:
    """Read ASCII portrait lines from `source_path`, stripping blank outer rows and shared indent."""
    lines = source_path.read_text(encoding="utf-8").split("\n")
    non_empty_indices = [idx for idx, line in enumerate(lines) if line.strip()]
    if not non_empty_indices:
        raise SystemExit(f"{source_path} has no content")
    body = [line.rstrip() for line in lines[non_empty_indices[0] : non_empty_indices[-1] + 1]]
    common_indent = min(len(line) - len(line.lstrip()) for line in body if line.strip())
    return [line[common_indent:] for line in body]


def build_panel(x_origin: int, y_origin: float) -> tuple[list[str], int]:
    """Render the right-side neofetch panel starting at `(x_origin, y_origin)`."""
    stats = load_stats()
    rows: list[Row | None] = [rule_row(TITLE, bold=True)]

    for entry in INFO:
        if entry is None:
            rows.append(None)
            continue
        key_label, value_text = entry
        if key_label == "Uptime":
            rows.append(info_row(key_label, compute_uptime(), element_id="age_data"))
        else:
            rows.append(info_row(key_label, value_text))

    rows.append(None)
    rows.append(rule_row("- Contact"))
    rows.extend(info_row(key_label, value_text) for key_label, value_text in CONTACT)

    rows.append(None)
    rows.append(rule_row("- GitHub Stats"))
    rows.append(
        Row()
        .text(". ", css_class="cc")
        .key("Repos")
        .text(":")
        .text(" ", css_class="cc")
        .fill(element_id="repo_data_dots")
        .text(" ", css_class="cc")
        .value(stats["repos"], "repo_data")
        .text(" {")
        .text("Contributed", css_class="key")
        .text(": ")
        .value(stats["contrib"], "contrib_data")
        .text("}")
        .text(" | ")
        .key("Stars")
        .text(":")
        .text(" ", css_class="cc")
        .fill(element_id="star_data_dots")
        .text(" ", css_class="cc")
        .value(stats["stars"], "star_data")
    )
    rows.append(
        Row()
        .text(". ", css_class="cc")
        .key("Commits")
        .text(":")
        .text(" ", css_class="cc")
        .fill(element_id="commit_data_dots")
        .text(" ", css_class="cc")
        .value(stats["commits"], "commit_data")
        .text(" | ")
        .key("Followers")
        .text(":")
        .text(" ", css_class="cc")
        .fill(element_id="follower_data_dots")
        .text(" ", css_class="cc")
        .value(stats["followers"], "follower_data")
    )
    rows.append(
        Row()
        .text(". ", css_class="cc")
        .key("Lines of Code")
        .text(":")
        .text(" ", css_class="cc")
        .fill(element_id="loc_data_dots")
        .text(" ", css_class="cc")
        .value(stats["loc"], "loc_data")
        .text(" ( ")
        .text(stats["added"], css_class="addColor", element_id="loc_add")
        .text("++", css_class="addColor")
        .text(", ")
        .text(stats["deleted"], css_class="delColor", element_id="loc_del")
        .text("--", css_class="delColor")
        .text(" )")
    )

    rendered_lines: list[str] = []
    for index, row in enumerate(rows):
        y_pos = y_origin + index * PANEL_LINE
        if row is None:
            rendered_lines.append(f'<tspan x="{x_origin}" y="{y_pos:g}" class="cc">.</tspan>')
        else:
            rendered_lines.append(row.render(x_origin, y_pos, PANEL_COLS))

    prompt_y = y_origin + (len(rows) + 1) * PANEL_LINE
    rendered_lines.append(
        f'<tspan x="{x_origin}" y="{prompt_y:g}">'
        f'<tspan class="key">&gt; </tspan>'
        f'<tspan class="value">█'
        f'<animate attributeName="opacity" values="1;0" dur="1.06s"'
        f' calcMode="discrete" repeatCount="indefinite"/>'
        f"</tspan></tspan>"
    )
    return rendered_lines, len(rows) + 2


def build_svg(theme_name: str) -> str:
    """Assemble the complete SVG markup for `theme_name` (`dark` or `light`)."""
    palette = THEMES[theme_name]
    art_lines = load_art(palette["art_src"])
    art_cols = max(len(line) for line in art_lines)
    art_font, art_line_height = art_metrics(art_cols)

    panel_x = int(MARGIN + ART_COL_WIDTH + GUTTER)
    _, panel_rows = build_panel(panel_x, 0.0)

    # Center both art and panel blocks on a shared horizontal axis.
    panel_span = (panel_rows - 1) * PANEL_LINE
    art_span = (len(art_lines) - 1) * art_line_height
    half_height = max(panel_span / 2 + LINE_PAD * PANEL_FONT, art_span / 2 + LINE_PAD * art_font)
    center_axis = MARGIN + half_height

    panel_lines, _ = build_panel(panel_x, center_axis - panel_span / 2 + LINE_MID * PANEL_FONT)
    art_y0 = center_axis - art_span / 2 + LINE_MID * art_font

    svg_width = int(panel_x + PANEL_COLS * PANEL_FONT * ADVANCE + MARGIN)
    svg_height = round(2 * center_axis)

    art_tspans = "\n".join(
        f'<tspan x="{MARGIN}" y="{art_y0 + row_idx * art_line_height:.2f}">{escape_xml(line)}</tspan>'
        for row_idx, line in enumerate(art_lines)
    )

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}px" height="{svg_height}px"
     font-family="ConsolasFallback,Consolas,Menlo,monospace">
<style>
@font-face {{
  src: local('Consolas'), local('Consolas Bold');
  font-family: 'ConsolasFallback';
  font-display: swap;
  size-adjust: 109%;
}}
.key {{fill: {palette['key']};}}
.value {{fill: {palette['value']};}}
.title {{fill: {palette['key']}; font-weight: bold;}}
.addColor {{fill: {palette['add']};}}
.delColor {{fill: {palette['del']};}}
.cc {{fill: {palette['dots']};}}
text, tspan {{white-space: pre;}}
</style>
<rect width="{svg_width}px" height="{svg_height}px" fill="{palette['bg']}" rx="15"/>
<text fill="{palette['art']}" font-size="{art_font:.2f}px" class="ascii">
{art_tspans}
</text>
<text fill="{palette['fg']}" font-size="{PANEL_FONT:g}px">
{chr(10).join(panel_lines)}
</text>
</svg>
"""


def main() -> None:
    """Regenerate `dark_mode.svg` and `light_mode.svg` in the repository root."""
    for theme_name, palette in THEMES.items():
        art_lines = load_art(palette["art_src"])
        art_cols = max(len(line) for line in art_lines)
        art_font, art_line_height = art_metrics(art_cols)
        print(f"{theme_name:>5} art: {art_cols} cols x {len(art_lines)} lines -> {art_font:.2f}px / {art_line_height:.2f}px line")
    print(f"uptime   : {compute_uptime()}")
    print(f"stats    : {'cache/stats.json' if STATS_SRC.exists() else 'not fetched yet (placeholders)'}")
    for theme_name in THEMES:
        out_path = ROOT / f"{theme_name}_mode.svg"
        out_path.write_text(build_svg(theme_name), encoding="utf-8")
        print(f"wrote {out_path.name} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
