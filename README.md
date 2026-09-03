# foss4g2026-attendance-certificate

Generate and deliver **certificates of attendance for FOSS4G Hiroshima 2026**
([2026.foss4g.org](https://2026.foss4g.org/en/), 30 August – 5 September 2026,
Hiroshima, Japan).

The certificate states the event date range and is signed by two officials —
**Nobusuke Iwasaki** (President, OSGeo Japan Chapter) and **Kenya Tamura**
(CEO, Eukarya, Inc.).

## Workflows

The project is exposed as a single `click` command-line interface covering three
workflows:

1. **Build the certificate template** — a reusable SVG certificate template
   (`assets/certificate-template.svg`) that embeds the FOSS4G logo and defines a
   `{{ full_name }}` placeholder to fill per attendee.
2. **Generate PDFs** — render one PDF certificate per attendee from
   `assets/attendees.csv`, filling the template's placeholder. *(implemented as
   the `generate` command)*
3. **Send email** — email each attendee their certificate PDF as an attachment.

Long-running, per-attendee commands show progress with a [`rich`](https://rich.readthedocs.io/)
progress bar.

## Requirements

- **Python 3.11** (pinned via `.python-version`)
- [uv](https://github.com/astral-sh/uv) for dependency management
- A native **cairo** library (used by `cairosvg` to render SVG → PDF). On macOS,
  install it with `brew install cairo`. The CLI adds the Homebrew lib paths to
  the dyld search path automatically, so no extra environment variables are
  needed.

## Setup

```bash
uv sync          # install dependencies
uv run foss4gcert  # run the CLI entry point
```

Add dependencies with:

```bash
uv add <package>
```

## Development

Code is formatted with [ruff](https://docs.astral.sh/ruff/) (configured under
`[tool.ruff]` in `pyproject.toml`). Install it as a dev dependency, then format:

```bash
uv add --dev ruff      # one-time: install ruff
uv run ruff format .   # format all sources
uv run ruff format --check .   # verify formatting without writing changes
```

## Usage

Run the CLI via `uv run`:

```bash
uv run foss4gcert --help
```

### Generate certificates

Render one PDF per attendee from the CSV and template:

```bash
uv run foss4gcert generate
```

Options:

| Option | Default | Description |
| --- | --- | --- |
| `--csv` | `assets/attendees.csv` | Attendee CSV (Tito export). |
| `--template` | `assets/certificate-template.svg` | SVG template containing `{{ full_name }}` and `{{ name_font_family }}` placeholders. |
| `--output-dir` | `outputs` | Directory to write generated PDFs into. |
| `--checkin-only` / `--all-attendees` | `--checkin-only` | Only generate for attendees with a non-empty `Check-ins: Badgy` value (badge picked up on site). Pass `--all-attendees` for every non-void row. |

> **Fonts for non-Latin names.** cairosvg does no font fallback, so the name is
> rendered in a single font family picked per attendee from `NAME_FONT_CANDIDATES`
> in [`src/generate.py`](src/generate.py): Georgia for Latin names, then
> `Hiragino Mincho ProN W6` (macOS) for Japanese, then `Arial Unicode MS`. Without
> a covering font installed, those names render as empty boxes; on Linux install a
> CJK serif (e.g. Noto Serif CJK JP) and add it to that list. The run prints a
> warning for any name no candidate covers.

Examples:

```bash
# Only attendees who picked up their badge on site (default)
uv run foss4gcert generate

# Every non-void ticket, into a custom directory
uv run foss4gcert generate --all-attendees --output-dir build/certs
```

Each PDF is named `<Ticket Reference>_<Ticket Full Name>.pdf`. Voided/refunded
tickets and (by default) attendees without a badge check-in are skipped, and a
row missing a name or reference is reported and skipped without aborting the
batch. A summary of generated / skipped / failed
counts is printed at the end.

### Send certificates

Email each attendee their generated PDF via **Gmail SMTP**. Copy `.env.example`
to `.env` and fill in the SMTP credentials first:

```bash
cp .env.example .env   # then edit .env with your Gmail App Password
```

`.env` (git-ignored) provides `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
`SMTP_PASSWORD` (a Gmail **App Password** — requires 2-Step Verification), and
`SMTP_FROM`.

```bash
# 1. Dry run (default) — lists recipients, verifies every PDF, sends nothing
uv run foss4gcert send

# 2. Send yourself a real test (keeps the attendee's certificate)
uv run foss4gcert send --send --limit 1 --test-to you@example.com

# 3. Send the full batch for real
uv run foss4gcert send --send
```

Options:

| Option | Default | Description |
| --- | --- | --- |
| `--csv` | `assets/attendees.csv` | Attendee CSV (Tito export). |
| `--certificates-dir` | `outputs` | Directory holding the generated PDFs. |
| `--reply-to` | `registration@foss4g.org` | Address for the Reply-To header. |
| `--dry-run` / `--send` | `--dry-run` | Preview (default) vs. actually send. |
| `--only` | – | Only send to the row whose `Ticket Email` matches. |
| `--test-to` | – | Redirect every email to this test address (not logged as sent). |
| `--limit` | – | Send to at most N recipients this run. |
| `--checkin-only` / `--all-attendees` | `--checkin-only` | Only send to attendees with a non-empty `Check-ins: Badgy` value. Pass `--all-attendees` to send to every non-void row. |
| `--delay` | `1.0` | Seconds to wait between sends (SMTP throttle). |

Sent `Ticket Reference`s are recorded in `outputs/sent.log` and skipped on
re-run, so an interrupted or daily-capped batch resumes without double-sending.
Gmail caps sends per day (~500 free / ~2000 Workspace); with ~540 attendees a
free account may need two days — just re-run `--send` the next day.

## Download template

Download template files and signature files from the below URL.

https://drive.google.com/drive/folders/1Umpg7YrWilpZnjRib1j9oKcYOlJhZM82?usp=drive_link

Place them under `assets` folder.

## Data: `assets/attendees.csv`

Exported from Tito (~540 rows, one per ticket). Columns used by this project:

- `Ticket Full Name` — attendee's name (primary name on the certificate).
- `Ticket Email` — delivery address for the certificate.
- `Ticket Reference` — per-ticket unique id (e.g. `YFFI-1`), used in filenames.
- `Void Status` — voided/refunded tickets are skipped.
- `Check-ins: Badgy` — badge pick-up count, recorded on site. Non-empty means
  the person actually attended; this is the column `--checkin-only` uses. (The
  `Check-ins: Conference checkin` column is empty in the export and unused.)

Names with non-ASCII characters (e.g. `Narcélio de Sá`) are preserved as UTF-8
throughout.

## Project structure

```text
src/
  main.py                            # entry point (foss4gcert console script)
  cli/                               # click command group and subcommands
  generate.py                        # PDF generation implementation
  send.py                            # email-sending implementation
assets/
  certificate-template.svg           # SVG certificate template
  logo-01.svg                        # FOSS4G Hiroshima 2026 logo
  attendees.csv                      # attendee list (Tito export)
  signature-osgeojp.png              # signature images (git-ignored, optional)
  signature-tamura.png
.env.example                         # SMTP config template (copy to .env)
```

The CLI is installed as the `foss4gcert` console script (see
`[project.scripts]` in `pyproject.toml`); run it with `uv run foss4gcert`.

## Notes

- Secrets (e.g. SMTP credentials for the send workflow) are read from environment
  variables and never committed.
- The template and generation tolerate the signature images being absent.
