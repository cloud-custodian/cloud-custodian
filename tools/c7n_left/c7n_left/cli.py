# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from pathlib import Path
import sys

import click
from c7n.config import Config

from .entry import initialize_iac
from .output import get_reporter, report_outputs, summary_options
from .core import CollectionRunner, ExecutionFilter
from .utils import load_policies


log = logging.getLogger("c7n.iac")


@click.group()
def cli():
    """Shift Left Policy"""
    logging.basicConfig(level=logging.INFO)
    initialize_iac()


@cli.command()
@click.option("--format", default="terraform")
@click.option(
    "--filters", help="filter policies or resources as k=v pairs with globbing"
)
@click.option("-p", "--policy-dir", type=click.Path())
@click.option("-d", "--directory", type=click.Path())
@click.option("-o", "--output", default="cli", type=click.Choice(report_outputs.keys()))
@click.option("--output-file", type=click.File("w"), default="-")
@click.option("--output-query", default=None)
@click.option("--summary", default="policy", type=click.Choice(summary_options.keys()))
def run(
    format, policy_dir, directory, output, output_file, output_query, summary, filters
):
    """evaluate policies against IaC sources.

    c7n-left -p policy_dir -d terraform_root --filters "severity=HIGH"


    WARNING - CLI interface subject to change.
    """
    config = Config.empty(
        source_dir=Path(directory),
        policy_dir=Path(policy_dir),
        output=output,
        output_file=output_file,
        output_query=output_query,
        summary=summary,
        filters=filters,
    )
    exec_filter = ExecutionFilter.parse(config)
    config["exec_filter"] = exec_filter
    policies = exec_filter.filter_policies(load_policies(policy_dir, config))
    if not policies:
        log.warning("no policies found")
        sys.exit(1)
    reporter = get_reporter(config)
    runner = CollectionRunner(policies, config, reporter)
    sys.exit(int(runner.run()))


if __name__ == "__main__":  # pragma: no cover
    try:
        cli()
    except Exception:
        import pdb, traceback

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
