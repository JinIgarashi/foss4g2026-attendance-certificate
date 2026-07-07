"""Certificate CLI — the click command group."""

import click

from src.cli.generate import generate
from src.cli.send import send


@click.group()
def cli():
    """Certificates of attendance for FOSS4G Hiroshima 2026."""


cli.add_command(generate)
cli.add_command(send)
