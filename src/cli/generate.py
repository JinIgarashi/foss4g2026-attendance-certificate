"""CLI interface for the `generate` command."""

from pathlib import Path

import click

from src.generate import CHECKIN_COLUMN, generate_certificates


@click.command()
@click.option(
    "--csv",
    "csv_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("assets/attendees.csv"),
    show_default=True,
    help="Attendee CSV (Tito export).",
)
@click.option(
    "--template",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("assets/certificate-template.svg"),
    show_default=True,
    help="SVG certificate template with a {{ full_name }} placeholder.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("outputs"),
    show_default=True,
    help="Directory to write generated PDFs into.",
)
@click.option(
    "--checkin-only/--all-attendees",
    default=True,
    show_default=True,
    help=f"Only generate certificates for attendees with a non-empty "
    f"'{CHECKIN_COLUMN}' value (i.e. who picked up their badge on site). "
    f"Use --all-attendees to generate for every non-void row.",
)
def generate(csv_path: Path, template: Path, output_dir: Path, checkin_only: bool):
    """Render one PDF certificate per attendee from the CSV."""
    generate_certificates(csv_path, template, output_dir, checkin_only)
