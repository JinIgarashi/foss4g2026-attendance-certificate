"""CLI interface for the `send` command."""

from pathlib import Path

import click

from src.generate import CHECKIN_COLUMN
from src.send import DEFAULT_REPLY_TO, DEFAULT_SENT_LOG, send_certificates


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
    "--certificates-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("outputs"),
    show_default=True,
    help="Directory holding the generated PDF certificates.",
)
@click.option(
    "--sent-log",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_SENT_LOG,
    show_default=True,
    help="CSV log of send results (timestamp, reference, name, email, pdf, "
    "status, error).",
)
@click.option(
    "--reply-to",
    default=DEFAULT_REPLY_TO,
    show_default=True,
    help="Address for the Reply-To header.",
)
@click.option(
    "--dry-run/--send",
    default=True,
    show_default=True,
    help="Preview without sending (default), or actually send email.",
)
@click.option(
    "--only",
    default=None,
    help="Only send to the row whose Ticket Email matches this address.",
)
@click.option(
    "--test-to",
    default=None,
    help="Redirect every email to this test address (keeps each certificate; "
    "logged as status=test, so it never blocks a later real send).",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Send to at most this many recipients this run.",
)
@click.option(
    "--checkin-only/--all-attendees",
    default=True,
    show_default=True,
    help=f"Only send to attendees with a non-empty '{CHECKIN_COLUMN}' value "
    f"(i.e. who picked up their badge on site). "
    f"Use --all-attendees to send to every non-void row.",
)
@click.option(
    "--delay",
    type=float,
    default=1.0,
    show_default=True,
    help="Seconds to wait between sends (throttle for SMTP rate limits).",
)
def send(
    csv_path: Path,
    certificates_dir: Path,
    sent_log: Path,
    reply_to: str,
    dry_run: bool,
    only: str | None,
    test_to: str | None,
    limit: int | None,
    delay: float,
    checkin_only: bool,
):
    """Email each attendee their certificate PDF as an attachment."""
    send_certificates(
        csv_path=csv_path,
        certificates_dir=certificates_dir,
        reply_to=reply_to,
        dry_run=dry_run,
        limit=limit,
        only=only,
        test_to=test_to,
        delay=delay,
        checkin_only=checkin_only,
        sent_log=sent_log,
    )
