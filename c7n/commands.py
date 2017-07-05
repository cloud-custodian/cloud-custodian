# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from collections import Counter, defaultdict
from datetime import timedelta, datetime
from functools import wraps
import inspect
import json
import logging
import os
import pprint
import sys
import time

import yaml

from c7n.policy import Policy, PolicyCollection, load as policy_load
from c7n.reports import report as do_report
from c7n.utils import Bag, dumps, load_file
from c7n.manager import resources
from c7n.resources import load_resources
from c7n import schema


log = logging.getLogger('custodian.commands')


def policy_command(f):

    @wraps(f)
    def _load_policies(options):
        load_resources()
        vars = _load_vars(options)

        errors = 0
        all_policies = PolicyCollection.from_data({}, options)

        # for a default region for policy loading, we'll expand regions later.
        options.region = options.regions[0]

        for fp in options.configs:
            try:
                collection = policy_load(options, fp, vars=vars)
            except IOError:
                log.error('policy file does not exist ({})'.format(fp))
                errors += 1
                continue
            except ValueError as e:
                log.error('problem loading policy file ({})'.format(e.message))
                errors += 1
                continue

            if collection is None:
                log.debug('Loaded file {}. Contained no policies.'.format(fp))
            else:
                log.debug(
                    'Loaded file {}. Contains {} policies'.format(
                        fp, len(collection)))
                all_policies = all_policies + collection

        if errors > 0:
            log.error('Found {} errors.  Exiting.'.format(errors))
            sys.exit(1)

        # filter by name and resource type
        policies = all_policies.filter(
            getattr(options, 'policy_filter', None),
            getattr(options, 'resource_type', None))

        # expand by region, this results in a separate policy instance per region of execution.
        policies = policies.expand_regions(options.regions)

        if len(policies) == 0:
            _print_no_policies_warning(options, all_policies)
            # If we filtered out all the policies we want to exit with a
            # non-zero status. But if the policy file is empty then continue
            # on to the specific command to determine the exit status.
            if len(all_policies) > 0:
                sys.exit(1)

        # Do not allow multiple policies in a region with the same name,
        # even across files
        policies_by_region = defaultdict(list)
        for p in policies:
            policies_by_region[p.options.region].append(p)
        for region in policies_by_region.keys():
            counts = Counter([p.name for p in policies_by_region[region]])
            for policy, count in counts.iteritems():
                if count > 1:
                    log.error("duplicate policy name '{}'".format(policy))
                    sys.exit(1)

        return f(options, list(policies))

    return _load_policies


def _load_vars(options):
    vars = None
    if options.vars:
        try:
            vars = load_file(options.vars)
        except IOError as e:
            log.error('Problem loading vars file "{}": {}'.format(options.vars, e.strerror))
            sys.exit(1)

    # TODO - provide builtin vars here (such as account)

    return vars


def _print_no_policies_warning(options, policies):
    if options.policy_filter or options.resource_type:
        log.warning("Warning: no policies matched the filters provided.")

        log.warning("Filters:")
        if options.policy_filter:
            log.warning("    Policy name filter (-p): " + options.policy_filter)
        if options.resource_type:
            log.warning("    Resource type filter (-t): " + options.resource_type)

        log.warning("Available policies:")
        for policy in policies:
            log.warning("    - {} ({})".format(policy.name, policy.resource_type))
        if not policies:
            log.warning("    (none)")
    else:
        log.warning('Empty policy file(s).  Nothing to do.')


def validate(options):
    load_resources()
    if len(options.configs) < 1:
        log.error('no config files specified')
        sys.exit(1)

    used_policy_names = set()
    schm = schema.generate()
    errors = []
    for config_file in options.configs:
        config_file = os.path.expanduser(config_file)
        if not os.path.exists(config_file):
            raise ValueError("Invalid path for config %r" % config_file)

        options.dryrun = True
        format = config_file.rsplit('.', 1)[-1]
        with open(config_file) as fh:
            if format in ('yml', 'yaml'):
                data = yaml.safe_load(fh.read())
            if format in ('json',):
                data = json.load(fh)

        errors += schema.validate(data, schm)
        conf_policy_names = {p['name'] for p in data.get('policies', ())}
        dupes = conf_policy_names.intersection(used_policy_names)
        if len(dupes) >= 1:
            errors.append(ValueError(
                "Only one policy with a given name allowed, duplicates: %s" % (
                    ", ".join(dupes)
                )
            ))
        used_policy_names = used_policy_names.union(conf_policy_names)
        if not errors:
            null_config = Bag(dryrun=True, log_group=None, cache=None, assume_role="na")
            for p in data.get('policies', ()):
                try:
                    p = Policy(p, null_config, Bag())
                    p.validate()
                except Exception as e:
                    msg = "Policy: %s is invalid: %s" % (
                        p.get('name', 'unknown'), e)
                    errors.append(msg)
        if not errors:
            log.info("Configuration valid: {}".format(config_file))
            continue

        log.error("Configuration invalid: {}".format(config_file))
        for e in errors:
            log.error("%s" % e)
    if errors:
        sys.exit(1)


# This subcommand is disabled in cli.py.
# Commmeting it out for coverage purposes.
#
# @policy_command
# def access(options, policies):
#    permissions = set()
#    for p in policies:
#        permissions.update(p.get_permissions())
#    pprint.pprint(sorted(list(permissions)))


@policy_command
def run(options, policies):
    exit_code = 0
    for policy in policies:
        try:
            policy()
        except Exception:
            exit_code = 2
            if options.debug:
                raise
            log.exception(
                "Error while executing policy %s, continuing" % (
                    policy.name))
    if exit_code != 0:
        sys.exit(exit_code)


@policy_command
def report(options, policies):
    if len(policies) == 0:
        log.error('Error: must supply at least one policy')
        sys.exit(1)

    resources = set([p.resource_type for p in policies])
    if len(resources) > 1:
        log.error('Error: Report subcommand can accept multiple policies, '
                  'but they must all be for the same resource.')
        sys.exit(1)

    delta = timedelta(days=options.days)
    begin_date = datetime.now() - delta
    do_report(
        policies, begin_date, options, sys.stdout, raw_output_fh=options.raw)


@policy_command
def logs(options, policies):
    if len(policies) != 1:
        log.error("Log subcommand requires exactly one policy")
        sys.exit(1)

    policy = policies.pop()

    for e in policy.get_logs(options.start, options.end):
        print("%s: %s" % (
            time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(e['timestamp'] / 1000)),
            e['message']))


def _schema_get_docstring(starting_class):
    """ Given a class, return its docstring.

    If no docstring is present for the class, search base classes in MRO for a
    docstring.
    """
    for cls in inspect.getmro(starting_class):
        if inspect.getdoc(cls):
            return inspect.getdoc(cls)


def schema_completer(prefix):
    """ For tab-completion via argcomplete, return completion options.

    For the given prefix so far, return the possible options.  Note that
    filtering via startswith happens after this list is returned.
    """
    load_resources()
    components = prefix.split('.')

    # Completions for resource
    if len(components) == 1:
        choices = [r for r in resources.keys() if r.startswith(prefix)]
        if len(choices) == 1:
            choices += ['{}{}'.format(choices[0], '.')]
        return choices

    if components[0] not in resources.keys():
        return []

    # Completions for category
    if len(components) == 2:
        choices = ['{}.{}'.format(components[0], x)
                   for x in ('actions', 'filters') if x.startswith(components[1])]
        if len(choices) == 1:
            choices += ['{}{}'.format(choices[0], '.')]
        return choices

    # Completions for item
    elif len(components) == 3:
        resource_mapping = schema.resource_vocabulary()
        return ['{}.{}.{}'.format(components[0], components[1], x)
                for x in resource_mapping[components[0]][components[1]]]

    return []


def schema_cmd(options):
    """ Print info about the resources, actions and filters available. """
    if options.json:
        schema.json_dump(options.resource)
        return

    load_resources()
    resource_mapping = schema.resource_vocabulary()

    if options.summary:
        schema.summary(resource_mapping)
        return

    # Here are the formats for what we accept:
    # - No argument
    #   - List all available RESOURCES
    # - RESOURCE
    #   - List all available actions and filters for supplied RESOURCE
    # - RESOURCE.actions
    #   - List all available actions for supplied RESOURCE
    # - RESOURCE.actions.ACTION
    #   - Show class doc string and schema for supplied action
    # - RESOURCE.filters
    #   - List all available filters for supplied RESOURCE
    # - RESOURCE.filters.FILTER
    #   - Show class doc string and schema for supplied filter

    if not options.resource:
        resource_list = {'resources': sorted(resources.keys())}
        print(yaml.safe_dump(resource_list, default_flow_style=False))
        return

    # Format is RESOURCE.CATEGORY.ITEM
    components = options.resource.split('.')

    #
    # Handle resource
    #
    resource = components[0].lower()
    if resource not in resource_mapping:
        log.error('{} is not a valid resource'.format(resource))
        sys.exit(1)

    if len(components) == 1:
        del(resource_mapping[resource]['classes'])
        output = {resource: resource_mapping[resource]}
        print(yaml.safe_dump(output))
        return

    #
    # Handle category
    #
    category = components[1].lower()
    if category not in ('actions', 'filters'):
        log.error("Valid choices are 'actions' and 'filters'. You supplied '{}'".format(category))
        sys.exit(1)

    if len(components) == 2:
        output = "No {} available for resource {}.".format(category, resource)
        if category in resource_mapping[resource]:
            output = {resource: {
                category: resource_mapping[resource][category]}}
        print(yaml.safe_dump(output))
        return

    #
    # Handle item
    #
    item = components[2].lower()
    if item not in resource_mapping[resource][category]:
        log.error('{} is not in the {} list for resource {}'.format(item, category, resource))
        sys.exit(1)

    if len(components) == 3:
        cls = resource_mapping[resource]['classes'][category][item]

        # Print docstring
        docstring = _schema_get_docstring(cls)
        print("\nHelp\n----\n")
        if docstring:
            print(docstring)
        else:
            # Shouldn't ever hit this, so exclude from cover
            print("No help is available for this item.")  # pragma: no cover

        # Print schema
        print("\nSchema\n------\n")
        pp = pprint.PrettyPrinter(indent=4)
        if hasattr(cls, 'schema'):
            pp.pprint(cls.schema)
        else:
            # Shouldn't ever hit this, so exclude from cover
            print("No schema is available for this item.", file=sys.sterr)  # pragma: no cover
        print('')
        return

    # We received too much (e.g. s3.actions.foo.bar)
    log.error("Invalid selector '{}'.  Max of 3 components in the "
              "format RESOURCE.CATEGORY.ITEM".format(options.resource))
    sys.exit(1)


def _metrics_get_endpoints(options):
    """ Determine the start and end dates based on user-supplied options. """
    if bool(options.start) ^ bool(options.end):
        log.error('--start and --end must be specified together')
        sys.exit(1)

    if options.start and options.end:
        start = options.start
        end = options.end
    else:
        end = datetime.utcnow()
        start = end - timedelta(options.days)

    return start, end


@policy_command
def metrics_cmd(options, policies):
    start, end = _metrics_get_endpoints(options)
    data = {}
    for p in policies:
        log.info('Getting %s metrics', p)
        data[p.name] = p.get_metrics(start, end, options.period)
    print(dumps(data, indent=2))


def version_cmd(options):
    from c7n.version import version

    if not options.debug:
        print(version)
        return

    indent = 13
    pp = pprint.PrettyPrinter(indent=indent)

    print("\nPlease copy/paste the following info along with any bug reports:\n")
    print("Custodian:  ", version)
    pyversion = sys.version.replace('\n', '\n' + ' ' * indent)  # For readability
    print("Python:     ", pyversion)
    # os.uname is only available on recent versions of Unix
    try:
        print("Platform:   ", os.uname())
    except:  # pragma: no cover
        print("Platform:  ", sys.platform)
    print("Using venv: ", hasattr(sys, 'real_prefix'))
    print("PYTHONPATH: ")
    pp.pprint(sys.path)
