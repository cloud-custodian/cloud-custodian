# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
# PYTHON_ARGCOMPLETE_OK  (Must be in first 1024 bytes, so if tab completion
# is failing, move this above the license)

import argcomplete
import argparse
import importlib
import logging
import os
import pdb
import sys
import traceback
from datetime import datetime
from dateutil.parser import parse as date_parse
from c7n.commands import LoadSessionPolicyJson

try:
    from setproctitle import setproctitle
except ImportError:
    def setproctitle(t):
        return None

from c7n import deprecated
from c7n.config import Config

DEFAULT_REGION = 'us-east-1'

log = logging.getLogger('custodian.cli')


def _default_options(p, exclude=[]):
    """ Add basic options ot the subparser.

    `exclude` is a list of options to exclude from the default set.
    e.g.: ['region', 'log-group']
    """
    provider = p.add_argument_group(
        "provider", "AWS account information, defaults per the aws cli")

    if 'region' not in exclude:
        provider.add_argument(
            "-r", "--region", action='append', default=[],
            dest='regions', metavar='REGION',
            help="AWS Region to target.  Can be used multiple times")
    provider.add_argument(
        "--profile",
        help="Account Config File Profile to utilize (AWS/TencentCloud)")
    provider.add_argument("--assume", default=None, dest="assume_role",
                          help="Role or Service Account to assume")
    provider.add_argument("--external-id", default=None, dest="external_id",
                          help="External Id to provide when assuming a role")

    config = p.add_argument_group(
        "config", "Policy config file(s) and policy selectors")
    # -c is deprecated.  Supported for legacy reasons
    config.add_argument("-c", "--config", help=argparse.SUPPRESS)
    config.add_argument("configs", nargs='*',
                        help="Policy configuration file(s) or directory")
    config.add_argument("-p", "--policies", default=[], dest='policy_filters',
                        action='append', help="Only use named/matched policies")
    config.add_argument("-t", "--resource", default=[], dest='resource_types',
                        action='append',
                        help="Only use policies with the given resource type")

    output = p.add_argument_group("output", "Output control")
    output.add_argument("-v", "--verbose", action="count", help="Verbose logging")
    if 'quiet' not in exclude:
        output.add_argument("-q", "--quiet", action="count",
                            help="Less logging (repeatable, -qqq for no output)")
    else:
        output.add_argument("-q", "--quiet", action="count", help=argparse.SUPPRESS)
    output.add_argument("--debug", default=False, help=argparse.SUPPRESS,
                        action="store_true")

    if 'vars' not in exclude:
        p.add_argument('--vars', default=None,
                      help='Vars file to substitute into policy')
        p.set_defaults(vars=None)

    if 'log-group' not in exclude:
        p.add_argument(
            "-l", "--log-group", default=None,
            help="Location to send policy logs (Ex: AWS CloudWatch Log Group)")
    else:
        p.add_argument("--log-group", default=None, help=argparse.SUPPRESS)

    if 'output-dir' not in exclude:
        p.add_argument("-s", "--output-dir", required=True,
                       help="[REQUIRED] Directory or S3 URL For policy output")

    if 'cache' not in exclude:
        p.add_argument(
            "-f", "--cache", default="~/.cache/cloud-custodian.cache",
            help="Cache file (default %(default)s)")
        p.add_argument(
            "--cache-period", default=15, type=int,
            help="Cache validity in minutes (default %(default)i)")
    else:
        p.add_argument("--cache", default=None, help=argparse.SUPPRESS)
    if 'session-policy' not in exclude:
        p.add_argument("--session-policy", required=False, default=None,
                       action=LoadSessionPolicyJson,
                       help="[OPTIONAL] AWS IAM Policy Document to be used as a session policy")


def _report_options(p):
    """ Add options specific to the report subcommand. """
    _default_options(p, exclude=['cache', 'log-group', 'quiet'])
    p.add_argument(
        '--days', type=float, default=1,
        help="Number of days of history to consider")
    p.add_argument(
        '--raw', type=argparse.FileType('w'),
        help="Store raw json of collected records to given file path")
    p.add_argument(
        '--field', action='append', default=[], type=_key_val_pair,
        metavar='HEADER=FIELD',
        help='Repeatable. JMESPath of field to include in the output OR '
        'for a tag use prefix `tag:`. Special case fields `region` and'
        '`policy` are available')
    p.add_argument(
        '--no-default-fields', action="store_true",
        help='Exclude default fields for report.')
    p.add_argument(
        '--format', default='csv', choices=['csv', 'grid', 'simple', 'json'],
        help="Format to output data in (default: %(default)s). "
        "Options include simple, grid, csv, json")
    p.add_argument(
        '--all-findings', default=False, action="store_true",
        help="Outputs all findings per resource. Defaults to a single finding per resource. ")


def _metrics_options(p):
    """ Add options specific to metrics subcommand. """
    _default_options(p, exclude=['log-group', 'output-dir', 'cache', 'quiet'])

    p.add_argument(
        '--start', type=date_parse,
        help='Start date (requires --end, overrides --days)')
    p.add_argument(
        '--end', type=date_parse, help='End date')
    p.add_argument(
        '--days', type=int, default=14,
        help='Number of days of history to consider (default: %(default)i)')
    p.add_argument('--period', type=int, default=60 * 24 * 24)


def _logs_options(p):
    """ Add options specific to logs subcommand. """
    _default_options(p, exclude=['cache', 'quiet'])

    # default time range is 0 to "now" (to include all log entries)
    p.add_argument(
        '--start',
        default='the beginning',  # invalid, will result in 0
        help='Start date and/or time',
    )
    p.add_argument(
        '--end',
        default=datetime.now().strftime('%c'),
        help='End date and/or time',
    )


def _schema_options(p):
    """ Add options specific to schema subcommand. """

    p.add_argument(
        'resource', metavar='selector', nargs='?', default=None)
    p.add_argument(
        '--summary', action="store_true",
        help="Summarize counts of available resources, actions and filters")
    p.add_argument('--json', action="store_true",
        help="Export custodian's jsonschema")
    p.add_argument('--outline', action="store_true",
        help="Print outline of all resources and their actions and filters")
    p.add_argument("-v", "--verbose", action="count", help="Verbose logging")
    p.add_argument("-q", "--quiet", action="count", help=argparse.SUPPRESS)
    p.add_argument("--debug", default=False, help=argparse.SUPPRESS)


def _dryrun_option(p):
    p.add_argument(
        "-d", "--dryrun", "--dry-run", action="store_true",
        help="Don't execute actions but filter resources")


def _key_val_pair(value):
    """
    Type checker to ensure that --field values are of the format key=val
    """
    if '=' not in value:
        msg = 'values must be of the form `header=field`'
        raise argparse.ArgumentTypeError(msg)
    return value


def setup_parser():
    c7n_desc = "Cloud Custodian - Cloud fleet management"
    parser = argparse.ArgumentParser(description=c7n_desc)

    # Setting `dest` means we capture which subparser was used.
    subs = parser.add_subparsers(
        title='commands',
        dest='subparser')

    run_desc = "\n".join((
        "Execute the policies in a config file.",
        "",
        "Multiple regions can be passed in, as can the symbolic region 'all'. ",
        "",
        "When running across multiple regions, policies targeting resources in ",
        "regions where they do not exist will not be run. The output directory ",
        "when passing multiple regions is suffixed with the region. Resources ",
        "with global endpoints are run just once and are suffixed with the first ",
        "region passed in or us-east-1 if running against 'all' regions.",
        ""
    ))

    run = subs.add_parser(
        "run", description=run_desc,
        help="Execute the policies in a config file",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    run.set_defaults(command="c7n.commands.run")
    _default_options(run)
    _dryrun_option(run)
    run.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skips validation of policies (assumes you've run the validate command seperately).")

    metrics_help = ("Emit metrics to provider metrics. Specify 'aws', 'gcp', or 'azure'. "
            "For more details on aws metrics options, see: "
            "https://cloudcustodian.io/docs/aws/usage.html#metrics")

    run.add_argument(
        "-m", "--metrics-enabled", metavar="PROVIDER",
        default=None, nargs="?", const="aws",
        help=metrics_help)
    run.add_argument(
        "--trace",
        dest="tracer",
        help="Tracing integration",
        default=None, nargs="?", const="default")

    schema_desc = ("Browse the available vocabularies (resources, filters, modes, and "
                   "actions) for policy construction. The selector "
                   "is specified with RESOURCE[.CATEGORY[.ITEM]] "
                   "examples: s3, ebs.actions, or ec2.filters.instance-age")
    schema = subs.add_parser(
        'schema', description=schema_desc,
        help="Interactive cli docs for policy authors")
    schema.set_defaults(command="c7n.commands.schema_cmd")
    _schema_options(schema)

    report_desc = ("Report of resources that a policy matched/ran on. "
                   "The default output format is csv, but other formats "
                   "are available.")
    report = subs.add_parser(
        "report", description=report_desc,
        help="Tabular report on policy matched resources")
    report.set_defaults(command="c7n.commands.report")
    _report_options(report)

    logs = subs.add_parser(
        'logs')
    logs.set_defaults(command="c7n.commands.logs")
    _logs_options(logs)

    metrics = subs.add_parser('metrics')
    metrics.set_defaults(command="c7n.commands.metrics_cmd")
    _metrics_options(metrics)

    version = subs.add_parser(
        'version', help="Display installed version of custodian")
    version.set_defaults(command='c7n.commands.version_cmd')
    version.add_argument('-v', '--verbose', action="count", help="Verbose logging")
    version.add_argument("-q", "--quiet", action="count", help=argparse.SUPPRESS)
    version.add_argument(
        "--debug", action="store_true",
        help="Print info for bug reports")

    validate_desc = (
        "Validate config files against the json schema")
    validate = subs.add_parser(
        'validate', description=validate_desc, help=validate_desc)
    validate.set_defaults(command="c7n.commands.validate", check_deprecations="yes")
    validate.add_argument(
        "-c", "--config", help=argparse.SUPPRESS)
    validate.add_argument("configs", nargs='*',
                          help="Policy Configuration File(s)")
    validate.add_argument("-v", "--verbose", action="count", help="Verbose Logging")
    validate.add_argument("-q", "--quiet", action="count", help="Less logging (repeatable)")
    validate.add_argument("--debug", default=False, help=argparse.SUPPRESS)
    deprecations = validate.add_mutually_exclusive_group(required=False)
    deprecations.add_argument("--no-deps", dest="check_deprecations",
                              action='store_const', const=deprecated.SKIP,
                              help="Do not check for deprecations")
    deprecations.add_argument("--strict", dest="check_deprecations",
                              action='store_const', const=deprecated.STRICT,
                              help="Any deprecations will cause a non-zero exit code")

    return parser


def _setup_logger(options):
    level = 3 + (options.verbose or 0) - (options.quiet or 0)

    if level <= 0:
        # print nothing
        log_level = logging.CRITICAL + 1
    elif level == 1:
        log_level = logging.ERROR
    elif level == 2:
        log_level = logging.WARNING
    elif level == 3:
        # default
        log_level = logging.INFO
    else:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")

    external_log_level = logging.ERROR
    if level <= 0:
        external_log_level = logging.CRITICAL + 1
    elif level >= 5:
        external_log_level = logging.INFO

    logging.getLogger('botocore').setLevel(external_log_level)
    logging.getLogger('urllib3').setLevel(external_log_level)
    logging.getLogger('s3transfer').setLevel(external_log_level)
    logging.getLogger('urllib3').setLevel(logging.ERROR)


def main(args=None):
    parser = setup_parser()
    argcomplete.autocomplete(parser)
    options = parser.parse_args(args=args)
    if options.subparser is None:
        parser.print_help(file=sys.stderr)
        return sys.exit(2)

    _setup_logger(options)

    # Support the deprecated -c option
    if getattr(options, 'config', None) is not None:
        options.configs.append(options.config)

    config = Config.empty(**vars(options))

    try:
        command = options.command
        if not callable(command):
            command = getattr(
                importlib.import_module(command.rsplit('.', 1)[0]),
                command.rsplit('.', 1)[-1])

        # Set the process name to something cleaner
        process_name = [os.path.basename(sys.argv[0])]
        process_name.extend(sys.argv[1:])
        setproctitle(' '.join(process_name))
        command(config)
    except Exception:
        if not options.debug:
            raise
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])


if __name__ == '__main__':
    main()
