"""FOSS4G Hiroshima 2026 — email certificates to attendees (Gmail SMTP)."""

import csv
import os
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
)

# Reuse the exact skip rules and filename scheme used at generation time so the
# PDF we look up here matches what `generate` wrote.
from src.generate import _checked_in, _is_void, _sanitize

load_dotenv()

console = Console()

DEFAULT_REPLY_TO = "registration@foss4g.org"
EVENT_DATES = "30 August – 5 September 2026"

# Kept out of `outputs/` (hundreds of PDFs) so the log is easy to find.
DEFAULT_SENT_LOG = Path("assets/sent.log")
LOG_HEADER = ["timestamp", "reference", "name", "email", "pdf", "status", "error"]

EMAIL_SUBJECT = "Your FOSS4G Hiroshima 2026 Certificate of Attendance"

EMAIL_BODY = """\
Dear {name},

Thank you for attending FOSS4G Hiroshima 2026 ({dates}).

Please find your Certificate of Attendance attached to this email as a PDF.

If you also need a certificate for a workshop you attended, please email
{reply_to} with the name(s) of the workshop(s) you attended, and we will
handle it individually.

We hope you enjoyed the conference and look forward to seeing you again.

Best regards,
The FOSS4G Hiroshima 2026 Organizing Committee
"""


def _pdf_path(certificates_dir: Path, reference: str, name: str) -> Path:
    """The PDF path `generate` would have written for this attendee."""
    return certificates_dir / f"{_sanitize(reference)}_{_sanitize(name)}.pdf"


def _load_smtp_config() -> dict:
    """Read and validate SMTP settings from the environment (.env)."""
    config = {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": os.environ.get("SMTP_PORT", "587"),
        "username": os.environ.get("SMTP_USERNAME", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "sender": os.environ.get("SMTP_FROM", ""),
    }
    missing = [
        var
        for var, key in (
            ("SMTP_HOST", "host"),
            ("SMTP_USERNAME", "username"),
            ("SMTP_PASSWORD", "password"),
            ("SMTP_FROM", "sender"),
        )
        if not config[key].strip()
    ]
    if missing:
        raise _fail(
            "Missing SMTP settings: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill it in."
        )
    try:
        config["port"] = int(config["port"])
    except ValueError as exc:
        raise _fail(f"SMTP_PORT must be an integer, got {config['port']!r}") from exc
    return config


def _fail(message: str) -> SystemExit:
    """Print an error and return a SystemExit for the caller to raise."""
    console.print(f"[red]{message}[/]")
    return SystemExit(1)


def _load_sent(sent_log: Path) -> set:
    """References already delivered in a previous run (for resume-safe re-runs).

    Only `status=sent` rows count: `failed` and `test` rows are treated as not
    yet delivered, so a re-run retries them.
    """
    if not sent_log.exists():
        return set()

    sent = set()
    with sent_log.open(encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if not row or not row[0].strip():
                continue
            if row[0] == "timestamp":  # header
                continue
            if len(row) == 1:  # legacy format: bare reference per line
                sent.add(row[0].strip())
                continue
            if len(row) >= 6 and row[5].strip() == "sent":
                sent.add(row[1].strip())
    return sent


def _append_log(
    sent_log: Path,
    reference: str,
    name: str,
    address: str,
    pdf_path: Path,
    status: str,
    error: str = "",
) -> None:
    """Append one result row, writing the header first if the file is new."""
    new_file = not sent_log.exists()
    if new_file:
        sent_log.parent.mkdir(parents=True, exist_ok=True)
    with sent_log.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(LOG_HEADER)
        writer.writerow(
            [
                datetime.now().isoformat(timespec="seconds"),
                reference,
                name,
                address,
                pdf_path.name,
                status,
                error,
            ]
        )


def _build_message(
    sender: str,
    recipient: str,
    reply_to: str,
    name: str,
    pdf_path: Path,
) -> EmailMessage:
    """Construct the certificate email with the PDF attached."""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Reply-To"] = reply_to
    message["Subject"] = EMAIL_SUBJECT
    message.set_content(
        EMAIL_BODY.format(name=name, dates=EVENT_DATES, reply_to=reply_to)
    )
    message.add_attachment(
        pdf_path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )
    return message


def send_certificates(
    csv_path: Path,
    certificates_dir: Path,
    reply_to: str,
    dry_run: bool,
    limit: int | None,
    only: str | None,
    test_to: str | None,
    delay: float,
    checkin_only: bool = True,
    sent_log: Path = DEFAULT_SENT_LOG,
) -> None:
    """Email each attendee their certificate PDF as an attachment."""
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    already_sent = _load_sent(sent_log)

    # First pass: resolve the recipients we will actually attempt this run.
    recipients = []  # (reference, name, address, pdf_path)
    skipped = 0
    for row in rows:
        if _is_void(row):
            skipped += 1
            continue
        if checkin_only and not _checked_in(row):
            skipped += 1
            continue

        name = (row.get("Ticket Full Name") or "").strip()
        reference = (row.get("Ticket Reference") or "").strip()
        address = (row.get("Ticket Email") or "").strip()

        if not (name and reference and address):
            skipped += 1
            continue
        if only and address.lower() != only.lower():
            skipped += 1
            continue
        if reference in already_sent and not test_to:
            skipped += 1
            continue

        pdf_path = _pdf_path(certificates_dir, reference, name)
        if not pdf_path.exists():
            skipped += 1
            console.print(
                f"[yellow]No PDF for {reference} / {name} "
                f"(expected {pdf_path.name}); skipping[/]"
            )
            continue

        recipients.append((reference, name, address, pdf_path))
        if limit is not None and len(recipients) >= limit:
            break

    if not recipients:
        console.print("[yellow]No recipients to send to.[/]")
        return

    if dry_run:
        console.print(
            f"[bold]Dry run[/] — would send [green]{len(recipients)}[/] email(s), "
            f"Reply-To [cyan]{reply_to}[/]. No mail sent."
        )
        for reference, name, address, pdf_path in recipients:
            destination = test_to or address
            console.print(f"  {reference}  {name}  →  {destination}  [{pdf_path.name}]")
        console.print(f"[dim]Results would be logged to {sent_log}[/]")
        return

    config = _load_smtp_config()
    sender = config["sender"]

    sent = failed = 0
    columns = (
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    )
    with smtplib.SMTP(config["host"], config["port"]) as smtp:
        smtp.starttls()
        smtp.login(config["username"], config["password"])

        with Progress(*columns, console=console) as progress:
            task = progress.add_task("Sending certificates", total=len(recipients))
            for reference, name, address, pdf_path in recipients:
                progress.advance(task)
                destination = test_to or address
                message = _build_message(sender, destination, reply_to, name, pdf_path)
                try:
                    _send_with_retry(smtp, message)
                    sent += 1
                    # `test` rows never block a later real send.
                    status = "test" if test_to else "sent"
                    _append_log(
                        sent_log, reference, name, destination, pdf_path, status
                    )
                    progress.console.print(
                        f"[green]✓[/] {reference}  {name}  →  {destination}"
                    )
                except Exception as exc:  # noqa: BLE001 - one failure must not abort the batch
                    failed += 1
                    _append_log(
                        sent_log,
                        reference,
                        name,
                        destination,
                        pdf_path,
                        "failed",
                        str(exc),
                    )
                    progress.console.print(
                        f"[red]✗ Failed to send to {destination} "
                        f"({reference} / {name}): {exc}[/]"
                    )
                time.sleep(delay)

    console.print(
        f"\n[bold]Done.[/] sent=[green]{sent}[/] "
        f"skipped=[yellow]{skipped}[/] failed=[red]{failed}[/] "
        f"(total rows: {len(rows)})"
    )
    console.print(f"[dim]Log: {sent_log}[/]")
    if test_to:
        console.print(
            f"[cyan]Test mode:[/] all mail sent to {test_to}; "
            f"logged as status=test (does not block a later real send)."
        )


def _send_with_retry(smtp: smtplib.SMTP, message: EmailMessage) -> None:
    """Send a message, retrying once on a transient SMTP error."""
    try:
        smtp.send_message(message)
    except smtplib.SMTPException:
        time.sleep(2)
        smtp.send_message(message)
