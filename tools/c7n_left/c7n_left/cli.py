# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import itertools
import logging
from pathlib import Path
import sys

import click

from c7n.config import Config

from .core import CollectionRunner, ExecutionFilter, get_provider
from .entry import initialize_iac
from .output import get_reporter, report_outputs, summary_options
from .test import TestReporter, TestRunner
from .policy import load_policies
from .validate import validate_files

log = logging.getLogger("c7n.iac")


@click.group()
def cli():
    """Shift Left Policy"""
    logging.basicConfig(level=logging.INFO)
    initialize_iac()


@cli.command()
@click.option("-d", "--directory", type=click.Path(), help="IaC directory to evaluate")
@click.option(
    "--var-file",
    help="Load variables from the given file, can be used more than once",
    type=click.Path(exists=True, dir_okay=False),
    default=(),
    multiple=True,
)
@click.option(
    "--output-file",
    help="Output file (default stdout)",
    type=click.File("w"),
    default="-",
)
@click.option("--terraform-workspace", help="Terraform workspace", default="default")
@click.option(
    "--output-query",
    default=None,
    help="Use a jmespath expression to filter json output",
)
@click.option(
    "--err-invalid",
    is_flag=True,
    help="Fail/stop if there are errors present in the HCL",
)
def dump(directory, var_file, output_file, terraform_workspace, output_query, err_invalid):
    """Dump the parsed resource graph or subset"""
    config = get_config(
        directory,
        output="jsongraph",
        output_file=output_file,
        var_file=var_file,
        terraform_workspace=terraform_workspace,
        output_query=output_query,
        stop_on_hcl_errors=err_invalid,
    )
    reporter = get_reporter(config)
    config["reporter"] = reporter
    provider = get_provider(config.source_dir)
    provider.initialize(config)
    graph = provider.parse(
        config.source_dir,
        config.var_files,
        workspace=terraform_workspace,
        stop_on_hcl_errors=err_invalid,
    )
    reporter.on_execution_started([], graph)
    reporter.on_execution_ended()


@cli.command()
@click.option("--format", default="terraform")
@click.option("--filters", help="Filter policies or resources as k=v pairs with globbing")
@click.option(
    "--warn-on", help="Select policies to log instead of fail on via k=v pairs with globbing"
)
@click.option("-p", "--policy-dir", type=click.Path(), help="Directory with policies")
@click.option("-d", "--directory", type=click.Path(), help="IaC directory to evaluate")
@click.option(
    "-o",
    "--output",
    default="cli",
    help="Output format (default cli)",
    type=click.Choice([k for k in report_outputs.keys() if not k == "jsongraph"]),
)
@click.option(
    "--output-file",
    help="Output file (default stdout)",
    type=click.File("w"),
    default="-",
)
@click.option(
    "--var-file",
    help="Load variables from the given file, can be used more than once",
    type=click.Path(exists=True, dir_okay=False),
    default=(),
    multiple=True,
)
@click.option("--terraform-workspace", help="Terraform workspace", default="default")
@click.option(
    "--output-query",
    default=None,
    help="Use a jmespath expression to filter json output",
)
@click.option("--summary", default="policy", type=click.Choice(summary_options.keys()))
@click.option(
    "--err-invalid",
    is_flag=True,
    help="Fail/stop if there are errors present in the HCL",
)
def run(
    format,
    policy_dir,
    directory,
    output,
    output_file,
    var_file,
    terraform_workspace,
    output_query,
    summary,
    filters,
    warn_on,
    err_invalid,
    reporter=None,
):
    """evaluate policies against IaC sources.

    c7n-left -p policy_dir -d terraform_root --filters "severity=HIGH"


    WARNING - CLI interface subject to change.
    """
    config = get_config(
        directory,
        policy_dir,
        output=output,
        output_file=output_file,
        output_query=output_query,
        var_file=var_file,
        terraform_workspace=terraform_workspace,
        summary=summary,
        warn_on=warn_on,
        filters=filters,
        stop_on_hcl_errors=err_invalid,
    )
    policies = config.exec_filter.filter_policies(load_policies(policy_dir, config))
    if not policies:
        log.warning("no policies found")
        sys.exit(1)
    if reporter is None:
        reporter = get_reporter(config)
    config["reporter"] = reporter
    runner = CollectionRunner(policies, config, reporter)
    sys.exit(int(runner.run()))


@cli.command()
@click.option("-p", "--policy-dir", type=click.Path(), required=True)
@click.option("--filters", help="filter policies or resources as k=v pairs with globbing")
def test(policy_dir, filters):
    """Run policy tests."""
    policy_dir = Path(policy_dir)
    source_dir = policy_dir / "tests"

    config = get_config(source_dir, policy_dir, output_file=sys.stdout, filters=filters)
    reporter = TestReporter(None, config)
    policies = config.exec_filter.filter_policies(load_policies(policy_dir, config))
    runner = TestRunner(policies, config, reporter)
    sys.exit(int(runner.run()))


@cli.command()
@click.option("-p", "--policy-dir", type=click.Path(), help="Directory with policies")
def validate(policy_dir=None):
    """Validate configuration files"""

    glob_patterns = ("*.yml", "*.yaml", "*.json")
    policy_dir = Path(policy_dir)

    if not policy_dir.is_dir():
        log.error(f"Policy directory {policy_dir} does not exist.")
        sys.exit(1)

    # Find all policy files in the given directory that match the glob patterns
    policy_files = list(itertools.chain(*(policy_dir.rglob(pattern) for pattern in glob_patterns)))
    if not policy_files:
        log.warning(f"No policy files found in {policy_dir} during validation.")
        return

    file_errors = validate_files(policy_files)
    if file_errors:
        error_count = sum(map(len, file_errors.values()))
        log.error(f"Validation failed with {error_count} errors")
        for policy_file, errors in file_errors.items():
            log.error(f"In file: {policy_file}")
            for error in errors:
                log.error(error)
        sys.exit(1)


def get_config(
    directory=None,
    policy_dir=None,
    output=None,
    output_file=None,
    var_file=(),
    terraform_workspace="default",
    output_query=None,
    summary=None,
    filters=None,
    warn_on=None,
    format="terraform",
    stop_on_hcl_errors=False,
):
    config = Config.empty(
        source_dir=directory and Path(directory),
        policy_dir=policy_dir and Path(policy_dir),
        output=output,
        output_file=output_file,
        terraform_workspace=terraform_workspace,
        var_files=var_file,
        output_query=output_query,
        summary=summary,
        filters=filters,
        warn_on=warn_on,
        format=format,
        stop_on_hcl_errors=stop_on_hcl_errors,
    )
    config["exec_filter"] = ExecutionFilter.parse(config.filters)
    config["warn_filter"] = ExecutionFilter.parse(config.warn_on, severity_direction="gte")
    return config


if __name__ == "__main__":  # pragma: no cover
    try:
        cli()
    except Exception:
        import pdb, traceback

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
