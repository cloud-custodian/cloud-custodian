# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pygit2
import click
import docker
import json

from collections import defaultdict
from c7n.vendored.distutils import version
from datetime import datetime, timedelta
from dateutil.tz import tzoffset, tzutc
from dateutil.parser import parse as parse_date
from functools import reduce
import operator
import re

from c7n.resources import load_available
from c7n.schema import resource_outline


def commit_date(commit):
    tzinfo = tzoffset(None, timedelta(minutes=commit.author.offset))
    return datetime.fromtimestamp(float(commit.author.time), tzinfo)


aliases = {
    'c7n': 'core',
    'cli': 'core',
    'c7n_mailer': 'tools',
    'c7n_tencentcloud': 'tencentcloud',
    'c7n_kube': 'kubernetes',
    'tools/c7n_kube': 'kubernetes',
    'tools/c7n-left': 'shift-left',
    'c7n-left': 'shift-left',
    'mailer': 'tools',
    'utils': 'core',
    'cask': 'tools',
    'test': 'tests',
    'docker': 'core',
    'dockerfile': 'tools',
    'asg': 'aws',
    'build': 'tests',
    'aws lambda policy': 'aws',
    'tags': 'aws',
    'notify': 'core',
    'sechub': 'aws',
    'sns': 'aws',
    'actions': 'aws',
    'chore': 'core',
    'serverless': 'core',
    'packaging': 'tests',
    '0': 'release',
    'dep': 'core',
    'ci': 'tests'}

skip = set(('release', 'merge'))


def resolve_dateref(since, repo):
    try:
        since = repo.lookup_reference('refs/tags/%s' % since)
    except KeyError:
        since = parse_date(since).astimezone(tzutc())
    else:
        since = commit_date(since.peel())
    return since


def schema_outline_from_docker(tag):
    client = docker.from_env()
    result = None
    while True:
        try:
            result = client.containers.run(
                f"cloudcustodian/c7n:{tag}",
                "schema --outline --json"
            )
        except docker.errors.NotFound:
            print("missing docker hub image tagged %s" % tag)
            vtag = version.LooseVersion(tag).version

            tag = f"{vtag[0]}.{vtag[1]}.{vtag[2]-1}.0"
            print("trying docker hub image tagged %s" % tag)
        if result:
            break

    return json.loads(result)


def link(provider='aws', resource=None, category=None, element=None):
    if resource and '.' in resource:
        provider, resource = resource.split('.')
    if resource and category and element:
        return (
            f'[`{element}`]('
            f'https://cloudcustodian.io/docs/'
            f'{provider}/resources/{resource}.html'
            f'#{provider}-{resource}-{category}-{element}'
            f')'
        )
    elif resource and not category:
        return (
            f'[`{provider}.{resource}`]('
            f'https://cloudcustodian.io/docs/'
            f'{provider}/resources/{resource}.html'
            f')'
        )
    elif not resource and category:
        return (
            f'[`{element}`]('
            f'https://cloudcustodian.io/docs/'
            f'{provider}/resources/{provider}-common-{category}.html'
            f'#{provider}-common-{category}-{element}'
            f')'
        )
    else:
        raise ValueError()


def schema_diff(schema_old, schema_new, skip_provider=()):
    def listify(items, bt=True):
        if bt:
            return ", ".join([f'`{i}`' for i in items])
        else:
            return ", ".join(items)

    out = []
    resources_map = defaultdict(dict)
    for provider in schema_new:
        if provider in skip_provider:
            continue
        resources_old = schema_old.get(provider, [])
        resources_new = schema_new[provider]
        for resource in sorted(set(list(resources_old) + list(resources_new))):
            if resource not in resources_old:
                out.append(f"- {link(provider=provider, resource=resource)} added")
            elif resource not in resources_new:
                out.append(f"- `{resource}` removed")
            else:
                for category in ('actions', 'filters'):
                    resources_map[resource][f"{category}_added"] = [
                        item for item in resources_new[resource][category]
                        if item not in resources_old[resource][category]
                    ]
                    resources_map[resource][f"{category}_removed"] = [
                        item for item in resources_old[resource][category]
                        if item not in resources_new[resource][category]
                    ]

    # Account for globally added or removed actions and filters; we
    # don't want these to be repeated over and over for each resource:
    global_map = {}
    for category in ('actions', 'filters'):
        added = global_map[f"{category}_added"] = reduce(operator.and_, [
            set(rsrc[f"{category}_added"]) for rsrc in resources_map.values()])
        removed = global_map[f"{category}_removed"] = reduce(operator.and_, [
            set(rsrc[f"{category}_removed"]) for rsrc in resources_map.values()])
        if added:
            added_str = listify(
                [link(category=category, element=el) for el in added],
                bt=False,
            )
            out.append(f"- added common {category}: {added_str}")
        if removed:
            out.append(f"- removed common {category}: {listify(removed)}")
        for resource, attrs in resources_map.items():
            attrs[f'{category}_added'] = [
                item for item in attrs[f'{category}_added']
                if item not in added
            ]
            attrs[f'{category}_removed'] = [
                item for item in attrs[f'{category}_removed']
                if item not in removed
            ]

    for resource, attrs in resources_map.items():
        if any(change for change in attrs.values()):
            out.append(f"- `{resource}`")
            for category in ('actions', 'filters'):
                added = attrs[f'{category}_added']
                removed = attrs[f'{category}_removed']
                if added:
                    added = [
                        link(resource=resource, category=category, element=el)
                        for el in added
                    ]
                    out.append(f"  - added {category}: "
                               f"{listify(added, bt=False)}")
                if removed:
                    out.append(f"  - removed {category}: {listify(removed)}")

    return "\n".join(out) + "\n"


def get_last_release(repo):
    regex = re.compile(r'^refs/tags/[\d\.]+')
    versions = [
        version.LooseVersion(t.rsplit('/', 1)[-1])
        for t in repo.references
        if regex.match(t)
    ]
    versions = sorted(versions)
    return versions[-1].vstring


@click.command()
@click.option('--path', required=True)
@click.option('--output', required=True)
@click.option('--since')
@click.option('--end')
@click.option('--skip-provider', multiple=True)
@click.option('--user', multiple=True)
def main(path, output, since, end, user, skip_provider):
    repo = pygit2.Repository(path)
    if since in ('latest', 'current', 'last'):
        since = get_last_release(repo)
    if since:
        since_dateref = resolve_dateref(since, repo)
    if end:
        end_dateref = resolve_dateref(end, repo)

    groups = {}
    count = 0
    for commit in repo.walk(
            repo.head.target):
        cdate = commit_date(commit)
        if since and cdate <= since_dateref:
            break
        if end and cdate >= end_dateref:
            continue
        if user and commit.author.name not in user:
            continue

        parts = commit.message.strip().split(' ', 1)
        if not len(parts) > 1:
            print("bad commit %s %s" % (cdate, commit.message))
            category = 'other'
        else:
            category = parts[0]
        category = category.strip().lower()
        # try to aliases before we match on prefix (like tools)
        category = aliases.get(category, category)
        if '.' in category:
            category = category.split('.', 1)[0]
        if '/' in category:
            category = category.split('/', 1)[0]
        if category in aliases:
            category = aliases[category]

        message = commit.message.strip()
        if '\n' in message:
            message = message.split('\n')[0]

        found = False
        for s in skip:
            if category.startswith(s):
                found = True
                continue
        if found:
            continue
        if user:
            message = "%s - %s - %s" % (cdate.strftime("%Y/%m/%d"), commit.author.name, message)
        groups.setdefault(category, []).append(message)
        count += 1

    import pprint
    print('total commits %d' % count)
    pprint.pprint(dict([(k, len(groups[k])) for k in groups]))

    diff_md = ""
    if since and not end and since.count('.') > 2:
        schema_old = schema_outline_from_docker(since)
        load_available()
        schema_new = resource_outline()
        diff_md = schema_diff(schema_old, schema_new, skip_provider)

    with open(output, 'w') as fh:
        for k in sorted(groups):
            if k in skip:
                continue
            print("# %s" % k, file=fh)
            for c in sorted(groups[k]):
                print(" - %s" % c.strip(), file=fh)
            print("\n", file=fh)
        if diff_md.strip():
            print("# schema changes", file=fh)
            print(diff_md, file=fh)


if __name__ == '__main__':
    main()
