# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from collections import Counter, defaultdict
from datetime import timedelta, datetime
from functools import wraps
import json
import itertools
import logging
import argparse
import os
import sys
from typing import List

import yaml
from yaml.constructor import ConstructorError

from c7n import deprecated
from c7n.exceptions import ClientError, PolicyValidationError
from c7n.loader import SourceLocator
from c7n.provider import clouds
from c7n.policy import Policy, PolicyCollection, load as policy_load
from c7n.schema import ElementSchema, StructureParser, generate
from c7n.utils import load_file, local_session, SafeLoader, yaml_dump
from c7n.config import Bag, Config
from c7n.resources import (
    load_resources, load_available, load_providers, PROVIDER_NAMES)


log = logging.getLogger('custodian.commands')


def policy_command(f):

    @wraps(f)
    def _load_policies(options):

        validate = True
        if 'skip_validation' in options:
            validate = not options.skip_validation

        if not validate:
            log.debug('Policy validation disabled')

        vars = _load_vars(options)

        errors = 0
        all_policies = PolicyCollection.from_data({}, options)

        # for a default region for policy loading, we'll expand regions later.
        options.region = ""
        for fp in options.configs:
            try:
                collection = policy_load(options, fp, validate=validate, vars=vars)
            except IOError:
                log.error('policy file does not exist ({})'.format(fp))
                errors += 1
                continue
            except yaml.YAMLError as e:
                log.error(
                    "yaml syntax error loading policy file ({}) error:\n {}".format(
                        fp, e))
                errors += 1
                continue
            except ValueError as e:
                log.error('problem loading policy file ({}) error: {}'.format(
                    fp, str(e)))
                errors += 1
                continue
            except PolicyValidationError as e:
                log.error('invalid policy file: {} error: {}'.format(
                    fp, str(e)))
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
            getattr(options, 'policy_filters', []),
            getattr(options, 'resource_types', []))

        # provider initialization
        provider_policies = {}
        for p in policies:
            provider_policies.setdefault(p.provider_name, []).append(p)

        policies = PolicyCollection.from_data({}, options)
        for provider_name in provider_policies:
            provider = clouds[provider_name]()
            p_options = provider.initialize(options)
            policies += provider.initialize_policies(
                PolicyCollection(provider_policies[provider_name], p_options),
                p_options)

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
            for policy, count in counts.items():
                if count > 1:
                    log.error("duplicate policy name '{}'".format(policy))
                    sys.exit(1)

        # Variable expansion and non schema validation (not optional)
        for p in policies:
            p.expand_variables(p.get_variables())
            p.validate()

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
    if options.policy_filters or options.resource_types:
        log.warning("Warning: no policies matched the filters provided.")

        log.warning("Filters:")
        if options.policy_filters:
            log.warning("    Policy name filter (-p): {}".format(
                ", ".join(options.policy_filters)))
        if options.resource_types:
            log.warning("    Resource type filter (-t): {}".format(
                ", ".join(options.resource_types)))

        log.warning("Available policies:")
        for policy in policies:
            log.warning("    - {} ({})".format(policy.name, policy.resource_type))
        if not policies:
            log.warning("    (none)")
    else:
        log.warning('Empty policy file(s).  Nothing to do.')


class DuplicateKeyCheckLoader(SafeLoader):

    def construct_mapping(self, node, deep=False):
        if not isinstance(node, yaml.MappingNode):
            raise ConstructorError(None, None,
                    "expected a mapping node, but found %s" % node.id,
                    node.start_mark)
        key_set = set()
        for key_node, value_node in node.value:
            if not isinstance(key_node, yaml.ScalarNode):
                continue
            k = key_node.value
            if k in key_set:
                raise ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    "found duplicate key", key_node.start_mark)
            key_set.add(k)

        return super(DuplicateKeyCheckLoader, self).construct_mapping(node, deep)


def validate(options):
    from c7n import schema

    if len(options.configs) < 1:
        log.error('no config files specified')
        sys.exit(1)

    used_policy_names = set()
    structure = StructureParser()
    all_errors = {}
    found_deprecations = False
    footnotes = deprecated.Footnotes()

    for config_file in options.configs:
        errors = []

        config_file = os.path.expanduser(config_file)
        if not os.path.exists(config_file):
            raise ValueError("Invalid path for config %r" % config_file)

        options.dryrun = True
        fmt = config_file.rsplit('.', 1)[-1]

        with open(config_file) as fh:
            if fmt in ('yml', 'yaml', 'json'):
                # our loader is safe loader derived.
                data = yaml.load(fh.read(), Loader=DuplicateKeyCheckLoader)  # nosec nosemgrep
            else:
                log.error("The config file must end in .json, .yml or .yaml.")
                raise ValueError("The config file must end in .json, .yml or .yaml.")

        try:
            structure.validate(data)
        except PolicyValidationError as e:
            log.error("Configuration invalid: {}".format(config_file))
            log.error("%s" % e)
            all_errors[config_file] = e
            continue

        load_resources(structure.get_resource_types(data))
        schm = schema.generate()
        errors += schema.validate(data, schm)
        conf_policy_names = {
            p.get('name', 'unknown') for p in data.get('policies', ())}
        dupes = conf_policy_names.intersection(used_policy_names)
        if len(dupes) >= 1:
            errors.append(ValueError(
                "Only one policy with a given name allowed, duplicates: %s" % (
                    ", ".join(dupes)
                )
            ))
        used_policy_names = used_policy_names.union(conf_policy_names)
        source_locator = None
        if fmt in ('yml', 'yaml'):
            # For yaml files there is at least the expectation that the policy
            # name is on a line by itself. With JSON, the file could be one big
            # line. At this stage we are only attempting to find line number for
            # policies in yaml files.
            source_locator = SourceLocator(config_file)
        if not errors:
            null_config = Config.empty(dryrun=True, account_id='na', region='na')
            for p in data.get('policies', ()):
                try:
                    policy = Policy(p, null_config, Bag())
                    policy.validate()
                    # If the policy is invalid, there isn't much point checking
                    # for deprecated usage as there is no guarantee as to the
                    # state of the policy.
                    if options.check_deprecations != deprecated.SKIP:
                        report = deprecated.report(policy)
                        if report:
                            found_deprecations = True
                            log.warning("deprecated usage found in policy\n" +
                                        report.format(
                                            source_locator=source_locator,
                                            footnotes=footnotes))

                except Exception as e:
                    msg = "Policy: %s is invalid: %s" % (
                        p.get('name', 'unknown'), e)
                    errors.append(msg)
        if not errors:
            log.info("Configuration valid: {}".format(config_file))
            continue

        all_errors[config_file] = errors
        log.error("Configuration invalid: {}".format(config_file))
        for e in errors:
            log.error("%s" % e)
    if found_deprecations:
        notes = footnotes()
        if notes:
            log.warning("deprecation footnotes:\n" + notes)
        if options.check_deprecations == deprecated.STRICT:
            sys.exit(1)
    if all_errors:
        sys.exit(1)


@policy_command
def run(options, policies: List[Policy]) -> None:
    exit_code = 0

    # AWS - Sanity check that we have an assumable role before executing policies
    # Todo - move this behind provider interface
    if options.assume_role and [p for p in policies if p.provider_name == 'aws']:
        # the cli options we're being handed haven't been initialized by the
        # provider, instead use one of the provider's policy options.
        sample_aws = [p for p in policies if p.provider_name == 'aws'].pop()
        try:
            local_session(clouds['aws']().get_session_factory(sample_aws.options))
        except ClientError:
            log.exception("Unable to assume role %s", options.assume_role)
            sys.exit(1)

    errored_policies: List[str] = []
    for policy in policies:
        try:
            policy()
        except Exception:
            exit_code = 2
            errored_policies.append(policy.name)
            if options.debug:
                raise
            log.exception(
                "Error while executing policy %s, continuing" % (
                    policy.name))
    if exit_code != 0:
        log.error("The following policies had errors while executing\n - %s" % (
            "\n - ".join(errored_policies)))
        sys.exit(exit_code)


@policy_command
def report(options, policies):
    from c7n.reports import report as do_report
    if len(policies) == 0:
        log.error('Error: must supply at least one policy')
        sys.exit(1)

    resources = {p.resource_type for p in policies}
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
    log.warning("logs command has been removed")
    sys.exit(1)


def schema_cmd(options):
    """ Print info about the resources, actions and filters available. """
    from c7n import schema

    if options.outline:
        provider = options.resource and options.resource.lower().split('.')[0] or None
        load_available()
        outline = schema.resource_outline(provider)
        if options.json:
            print(json.dumps(outline, indent=2))
            return
        print(yaml_dump(outline))
        return

    if options.json:
        schema.json_dump(options.resource)
        return

    if options.summary:
        load_available()
        resource_mapping = schema.resource_vocabulary()
        schema.pprint_schema_summary(resource_mapping)
        return

    # Here are the formats for what we accept:
    # - No argument
    #   - List all available RESOURCES
    # - PROVIDER
    #   - List all available RESOURCES for supplied PROVIDER
    # - RESOURCE
    #   - List all available actions and filters for supplied RESOURCE
    # - MODE
    #   - List all available MODES
    # - RESOURCE.actions
    #   - List all available actions for supplied RESOURCE
    # - RESOURCE.actions.ACTION
    #   - Show class doc string and schema for supplied action
    # - RESOURCE.filters
    #   - List all available filters for supplied RESOURCE
    # - RESOURCE.filters.FILTER
    #   - Show class doc string and schema for supplied filter

    if not options.resource:
        load_available(resources=False)
        resource_list = {'resources': sorted(itertools.chain(
            *[clouds[p].resource_map.keys() for p in PROVIDER_NAMES if p in clouds]))}
        print(yaml_dump(resource_list))
        return

    # Format is [PROVIDER].RESOURCE.CATEGORY.ITEM
    # optional provider defaults to aws for compatibility
    components = options.resource.lower().split('.')

    if len(components) == 1 and components[0] in PROVIDER_NAMES:
        load_providers((components[0]))
        resource_list = {'resources': sorted(
            clouds[components[0]].resource_map.keys())}
        print(yaml_dump(resource_list))
        return
    if components[0] in PROVIDER_NAMES:
        cloud_provider = components.pop(0)
        components[0] = '%s.%s' % (cloud_provider, components[0])
        load_resources((components[0],))
        resource_mapping = schema.resource_vocabulary(
            cloud_provider, aliases=True)
    elif components[0] == 'mode':
        load_available(resources=False)
        resource_mapping = schema.resource_vocabulary()
    else:  # compatibility, aws is default for provider
        components[0] = 'aws.%s' % components[0]
        load_resources((components[0],))
        resource_mapping = schema.resource_vocabulary('aws', aliases=True)

    #
    # Handle mode
    #
    if components[0] == "mode":
        if len(components) == 1:
            output = {components[0]: list(resource_mapping[components[0]].keys())}
            print(yaml_dump(output))
            return

        if len(components) == 2:
            if components[1] not in resource_mapping[components[0]]:
                log.error('{} is not a valid mode'.format(components[1]))
                sys.exit(1)

            _print_cls_schema(resource_mapping[components[0]][components[1]])
            return

        # We received too much (e.g. mode.actions.foo)
        log.error("Invalid selector '{}'. Valid options are 'mode' "
                  "or 'mode.TYPE'".format(options.resource))
        sys.exit(1)
    #
    # Handle resource
    #
    resource = components[0]
    resource_info = resource_mapping.get(resource, resource_mapping['aliases'].get(resource))
    if resource_info is None:
        log.error('{} is not a valid resource'.format(resource))
        sys.exit(1)

    if len(components) == 1:
        docstring = ElementSchema.doc(
            resource_info['classes']['resource'])
        resource_info.pop('classes', None)
        # de-alias to preferred resource name
        resource = resource_info.pop('resource_type', resource)
        if docstring:
            print("\nHelp\n----\n")
            print(docstring + '\n')
        output = {resource: resource_info}
        print(yaml_dump(output))
        return

    #
    # Handle category
    #
    category = components[1]
    if category not in ('actions', 'filters'):
        log.error("Valid choices are 'actions' and 'filters'. You supplied '{}'".format(category))
        sys.exit(1)

    if len(components) == 2:
        output = "No {} available for resource {}.".format(category, resource)
        if category in resource_info:
            output = {resource: {
                category: resource_info[category]}}
        print(yaml_dump(output))
        return

    #
    # Handle item
    #
    item = components[2]
    if item not in resource_info[category]:
        log.error('{} is not in the {} list for resource {}'.format(item, category, resource))
        sys.exit(1)

    if len(components) == 3:
        cls = resource_info['classes'][category][item]
        _print_cls_schema(cls)

        return

    # We received too much (e.g. s3.actions.foo.bar)
    log.error("Invalid selector '{}'.  Max of 3 components in the "
              "format RESOURCE.CATEGORY.ITEM".format(options.resource))
    sys.exit(1)


def _print_cls_schema(cls):
    # Print docstring
    docstring = ElementSchema.doc(cls)
    print("\nHelp\n----\n")
    if docstring:
        print(docstring)
    else:
        # Shouldn't ever hit this, so exclude from cover
        print("No help is available for this item.")  # pragma: no cover

    # Print schema
    print("\nSchema\n------\n")
    if hasattr(cls, 'schema'):
        definitions = generate()['definitions']
        component_schema = ElementSchema.schema(definitions, cls)
        print(yaml_dump(component_schema))
    else:
        # Shouldn't ever hit this, so exclude from cover
        print("No schema is available for this item.", file=sys.sterr)  # pragma: no cover
    print('')
    return


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
    log.warning("metrics command has been removed")
    sys.exit(1)


def version_cmd(options):
    from c7n.version import version
    from c7n.resources import load_available
    from c7n.mu import generate_requirements

    if not options.debug:
        print(version)
        return

    indent = 13

    print("\nPlease copy/paste the following info along with any bug reports:\n")
    print("Custodian:  ", version)
    pyversion = sys.version.replace('\n', '\n' + ' ' * indent)  # For readability
    print("Python:     ", pyversion)
    # os.uname is only available on recent versions of Unix
    try:
        print("Platform:   ", os.uname())
    except Exception:  # pragma: no cover
        print("Platform:  ", sys.platform)

    is_venv = (
        hasattr(sys, 'real_prefix') or
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
    print("Using venv: ", is_venv)
    in_container = os.path.exists('/.dockerenv')
    print("Docker: %s" % str(bool(in_container)))
    print("Installed: \n")

    packages = ['c7n']
    found = load_available(resources=False)
    if 'gcp' in found:
        packages.append('c7n_gcp')
    if 'azure' in found:
        packages.append('c7n_azure')
    if 'k8s' in found:
        packages.append('c7n_kube')
    if 'openstack' in found:
        packages.append('c7n_openstack')
    if 'aliyun' in found:
        packages.append('c7n_aliyun')
    if 'vsphere' in found:
        packages.append('c7n_vsphere')
    print(generate_requirements(packages))


class LoadSessionPolicyJson(argparse.Action):

    @staticmethod
    def load_session_policy_from_file(session_pol_file_name):
        # try to read json object
        try:
            with open(session_pol_file_name, "r") as sp:
                s_pol = json.load(sp)
            return s_pol
        except Exception as e:
            raise e

    def __call__(self, parser, namespace, values, option_string=None):
        file_name = values
        p = self.load_session_policy_from_file(file_name)
        setattr(namespace, self.dest, p)
