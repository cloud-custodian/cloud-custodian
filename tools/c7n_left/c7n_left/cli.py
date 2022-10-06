# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from pathlib import Path

import click
from c7n.config import Config

from .entry import initialize_iac
from .output import get_reporter, report_outputs
from .core import CollectionRunner
from .utils import load_policies


@click.group()
def cli():
    """Shift Left Policy"""
    logging.basicConfig(level=logging.DEBUG)
    initialize_iac()


@cli.command()
@click.option("--format", default="terraform")
@click.option("-p", "--policy-dir", type=click.Path())
@click.option("-d", "--directory", type=click.Path())
@click.option("-o", "--output", default="cli", type=click.Choice(report_outputs.keys()))
@click.option("--output-file", type=click.File("w"), default="-")
def run(format, policy_dir, directory, output, output_file):
    """evaluate policies against IaC sources.

    WARNING - CLI interface subject to change.
    """
    config = Config.empty(
        source_dir=Path(directory),
        policy_dir=Path(policy_dir),
        output=output,
        output_file=output_file,
    )
    policies = load_policies(policy_dir, config)
    reporter = get_reporter(config)
    runner = CollectionRunner(policies, config, reporter)
    runner.run()


if __name__ == "__main__":  # pragma: no cover
    try:
        cli()
    except Exception:
        import pdb, sys, traceback

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
