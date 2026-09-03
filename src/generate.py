"""FOSS4G Hiroshima 2026 — certificate generation implementation."""

import csv
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape


def _ensure_cairo_on_path() -> None:
    """Help cairocffi find the native cairo library on macOS.

    Homebrew installs libcairo under /opt/homebrew/lib (Apple Silicon) or
    /usr/local/lib (Intel), which are not on the default dyld search path. Add
    them before cairosvg is imported so `uv run main.py` works without the
    caller exporting DYLD_FALLBACK_LIBRARY_PATH themselves.
    """
    if sys.platform != "darwin":
        return
    var = "DYLD_FALLBACK_LIBRARY_PATH"
    existing = os.environ.get(var, "")
    paths = existing.split(os.pathsep) if existing else []
    for candidate in ("/opt/homebrew/lib", "/usr/local/lib"):
        if os.path.isdir(candidate) and candidate not in paths:
            paths.append(candidate)
    if paths:
        os.environ[var] = os.pathsep.join(paths)


_ensure_cairo_on_path()

import cairocffi  # noqa: E402 - must follow _ensure_cairo_on_path()
import cairosvg  # noqa: E402 - must follow _ensure_cairo_on_path()
from rich.console import Console  # noqa: E402
from rich.progress import (  # noqa: E402
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
)

console = Console()

NAME_PLACEHOLDER = "{{ full_name }}"
FONT_PLACEHOLDER = "{{ name_font_family }}"
CHECKIN_COLUMN = "Check-ins: Badgy"

# Font families tried, in order, for the attendee name. cairosvg does no font
# fallback: it takes only the first family of a font-family list and hands it to
# cairo's toy text API, which renders .notdef boxes ("tofu") for every character
# that one font lacks. So we pick, per name, the first family that covers all of
# its characters -- Latin names keep the certificate's Georgia look, and only
# names that need it switch. The last entry is the catch-all.
NAME_FONT_CANDIDATES = (
    "Georgia",
    # W6 is the bold weight: the plain family name resolves to W3, which
    # looks noticeably lighter than the Georgia-Bold used for Latin names.
    "Hiragino Mincho ProN W6",
    "Hiragino Mincho ProN",
    "Arial Unicode MS",
)


def _is_void(row: dict) -> bool:
    """True when the ticket's Void Status marks it void/refunded."""
    status = (row.get("Void Status") or "").strip().lower()
    return status not in ("", "no", "false", "none")


def _checked_in(row: dict) -> bool:
    """True when the attendee has a badge check-in recorded.

    Tito records a count in this column when the badge was handed over on
    site, so any non-empty value means the person actually attended.
    """
    return bool((row.get(CHECKIN_COLUMN) or "").strip())


def _normalize_name(name: str) -> str:
    """Tidy a name for display: no ideographic spaces, no double spaces.

    U+3000 (IDEOGRAPHIC SPACE) shows up in the Tito export between the parts of
    some names. Georgia has no glyph for it, so leaving it in would push an
    otherwise Latin name onto a CJK font; a plain space keeps it in Georgia.
    """
    return re.sub(r"\s+", " ", name.replace("\u3000", " ")).strip()


@lru_cache(maxsize=None)
def _scaled_font(family: str):
    """The bold scaled font cairo resolves for `family`."""
    surface = cairocffi.PDFSurface(None, 1, 1)
    context = cairocffi.Context(surface)
    context.select_font_face(
        family, cairocffi.FONT_SLANT_NORMAL, cairocffi.FONT_WEIGHT_BOLD
    )
    return context.get_scaled_font()


@lru_cache(maxsize=None)
def _uncovered(family: str, text: str) -> str:
    """The characters of `text` that `family` would render as .notdef boxes."""
    glyphs, _clusters, _flags = _scaled_font(family).text_to_glyphs(0, 0, text, True)
    # Each glyph is an (index, x, y) tuple, one per character for these simple
    # strings; glyph index 0 is .notdef, i.e. tofu.
    return "".join(char for char, (index, _x, _y) in zip(text, glyphs) if index == 0)


def _font_family_for(name: str) -> str:
    """First candidate family whose glyphs cover every character of `name`."""
    for family in NAME_FONT_CANDIDATES:
        if not _uncovered(family, name):
            return family
    fallback = NAME_FONT_CANDIDATES[-1]
    console.print(
        f"[yellow]No installed font covers "
        f"'{_uncovered(fallback, name)}' in '{name}'; "
        f"falling back to {fallback} (some characters will render as boxes)[/]"
    )
    return fallback


def _sanitize(value: str) -> str:
    """Make a string safe for use in a filename."""
    value = value.strip()
    # Drop characters that are illegal/awkward in filenames across OSes.
    value = re.sub(r'[/\\:*?"<>|]', "", value)
    # Collapse any run of whitespace into a single underscore.
    value = re.sub(r"\s+", "_", value)
    return value


def generate_certificates(
    csv_path: Path,
    template: Path,
    output_dir: Path,
    checkin_only: bool,
) -> None:
    """Render one PDF certificate per attendee from the CSV."""
    template_svg = template.read_text(encoding="utf-8")
    template_url = str(template.resolve())

    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    output_dir.mkdir(parents=True, exist_ok=True)

    generated = skipped = failed = restyled = 0

    columns = (
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    )
    with Progress(*columns, console=console) as progress:
        task = progress.add_task("Generating certificates", total=len(rows))
        for row in rows:
            progress.advance(task)

            if _is_void(row):
                skipped += 1
                continue
            if checkin_only and not _checked_in(row):
                skipped += 1
                continue

            name = _normalize_name(row.get("Ticket Full Name") or "")
            reference = (row.get("Ticket Reference") or "").strip()

            if not name:
                failed += 1
                console.print(
                    f"[yellow]Skipping row with reference "
                    f"{reference or '(none)'}: empty Ticket Full Name[/]"
                )
                continue
            if not reference:
                failed += 1
                console.print(f"[yellow]Skipping '{name}': empty Ticket Reference[/]")
                continue

            font_family = _font_family_for(name)
            if font_family != NAME_FONT_CANDIDATES[0]:
                restyled += 1
            filled_svg = template_svg.replace(NAME_PLACEHOLDER, escape(name)).replace(
                FONT_PLACEHOLDER, escape(font_family)
            )
            out_path = output_dir / f"{_sanitize(reference)}_{_sanitize(name)}.pdf"

            try:
                cairosvg.svg2pdf(
                    bytestring=filled_svg.encode("utf-8"),
                    write_to=str(out_path),
                    url=template_url,
                    unsafe=True,
                )
                generated += 1
            except Exception as exc:  # noqa: BLE001 - one bad row must not abort the batch
                failed += 1
                console.print(
                    f"[red]Failed to render certificate for "
                    f"{reference} / {name}: {exc}[/]"
                )

    console.print(
        f"\n[bold]Done.[/] generated=[green]{generated}[/] "
        f"skipped=[yellow]{skipped}[/] failed=[red]{failed}[/] "
        f"(total rows: {len(rows)})"
    )
    if restyled:
        console.print(
            f"{restyled} name(s) needed a non-default font "
            f"(not {NAME_FONT_CANDIDATES[0]})"
        )
    console.print(f"PDFs written to [bold]{output_dir}[/]")
