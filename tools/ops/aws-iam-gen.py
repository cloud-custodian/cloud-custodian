# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
"""
Tool to generate a list of iam permissions from a
directory of policies.
"""

import click
from collections import defaultdict
import functools
import json
from pathlib import Path
import yaml

from c7n import resources, config, loader
from c7n.resources import aws


@click.group()
def cli():
    """aws iam permissions generation"""


@cli.command()
@click.option("-f", "--iam-file", type=click.File("rb"), multiple=True)
@click.option("--output", type=click.File("w"), default="-")
def merge(iam_file, output):
    """Merge multiple iam permission files"""
    perms = set()
    for f in iam_file:
        perms.update(yaml.safe_load(f.read()))
    output.write(yaml.dump(sorted(perms), default_flow_style=False))


@cli.command()
@click.option("-d", "--directory", required=True)
@click.option("--name-glob", multiple=True)
@click.option("--output", type=click.File("w"), default="-")
def from_policy(directory, name_glob, output):
    """Generate an iam permission list from a directory of custodian policy files"""
    ploader = loader.PolicyLoader(config.Config.empty())
    pdir = Path(directory)
    collections = []
    for f in pdir.rglob("*.y*ml"):
        collections.append(ploader.load_file(f))
    policies = functools.reduce(lambda x, y: x + y, collections)
    if name_glob:
        policies = policies.filter(name_glob)
    [p.validate() for p in policies]
    print(len(policies))
    mperms = get_collection_permissions(policies)
    print(json.dumps(mperms, indent=2), file=output)


@cli.command()
@click.option("-r", "--rtype", multiple=True)
@click.option("-s", "--service", multiple=True)
@click.option("--output", type=click.File("w"), default="-")
def discovery(rtype, service, output):
    """Generate a permissions file from supported custodian resource types"""
    skip_services = set(service)
    skip_rtypes = set(rtype)

    resources.load_resources()
    ploader = loader.PolicyLoader(config.Config.empty())
    pdata = []
    for rtype, rvalue in aws.AWS.resources.items():
        if rtype in skip_rtypes:
            continue
        if rvalue.resource_type.service in skip_services:
            continue
        pdata.append({"name": rtype, "resource": "aws.%s" % rtype})
    policies = ploader.load_data({"policies": pdata}, ":mem:")
    mperms = get_collection_permissions(policies)
    print(json.dumps(mperms, indent=2), file=output)


def get_collection_permissions(policies):
    perms = set()
    for p in policies:
        perms.update(p.get_permissions())
    mperms = get_minimal_permissions(perms)
    return mperms


def get_minimal_permissions(perms):
    # pprint.pprint(sorted(perms))
    print("Perm Count: %d" % (len(perms)))
    print("Size: %d" % len(json.dumps(list(perms), indent=0)))

    min_perms = []
    grouped_perms = parse_and_group_services(list(perms))

    for service, permissions in grouped_perms.items():
        min_perms.extend(["%s:%s" % (service, pat) for pat in minimize_perms(permissions)])

    print("Perm Count: %d" % (len(min_perms)))
    print("Size: %d" % len(json.dumps(list(min_perms), indent=0)))
    return sorted(min_perms)


def parse_and_group_services(strings):
    """
        Parses a list of strings in 'service:permission' format and groups them by service.

        Args:
            strings (list): List of strings in the form ['service1:perm1', ...]

        Returns:
    ,        dict: A dictionary mapping each service to a list of its permissions.
    """
    services = {}
    for s in strings:
        parts = s.split(":")
        if len(parts) != 2:
            continue  # skip invalidly formatted strings
        service, permission = parts[0], parts[1]
        if service not in services:
            services[service] = []
        services[service].append(permission)
    return services


def minimize_perms(permissions):
    groups = defaultdict(list)
    for s in permissions:
        if s.startswith("Get"):
            key = "Get"
        elif s.startswith("Describe"):
            key = "Describe"
        elif s.startswith("List"):
            key = "List"
        elif s.startswith("BatchGet"):
            key = "BatchGet"
        elif s.startswith("Search"):
            key = "Search"
        elif s.startswith("View"):
            key = "View"
        elif len(s) >= 4:
            print(s)
            key = s[:4]
        else:
            key = s
        groups[key].append(s)

    return [f"{key}*" for key in groups.keys()]


if __name__ == "__main__":
    try:
        cli()
    except Exception:
        import traceback, pdb, sys

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
