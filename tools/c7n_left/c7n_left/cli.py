import logging
from pathlib import Path

import click
from c7n.config import Config

from .output import get_reporter
from .provider import CollectionRunner
from .utils import load_policies


@click.group()
def cli():
    """Shift Left Policy"""
    logging.basicConfig(level=logging.DEBUG)


@cli.command()
@click.option("--format", default="terraform")
@click.option("-p", "--policy-dir", type=click.Path())
@click.option("-d", "--directory", type=click.Path())
@click.option("-o", "--output", type=click.Path())
def run(format, policy_dir, directory, output):
    """evaluate policies against iaac sources"""
    config = Config.empty(
        source_dir=Path(directory), policy_dir=Path(policy_dir), output=output
    )
    policies = load_policies(policy_dir, config)
    reporter = get_reporter(config)
    runner = CollectionRunner(policies, config, reporter)
    runner.run()


if __name__ == "__main__":
    try:
        cli()
    except Exception:
        import pdb, sys, traceback

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
