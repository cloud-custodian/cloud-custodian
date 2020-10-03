# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pygit2
import click

from datetime import datetime, timedelta
from dateutil.tz import tzoffset, tzutc
from dateutil.parser import parse as parse_date


def commit_date(commit):
    tzinfo = tzoffset(None, timedelta(minutes=commit.author.offset))
    return datetime.fromtimestamp(float(commit.author.time), tzinfo)


aliases = {
    'c7n': 'core',
    'cli': 'core',
    'c7n_mailer': 'tools',
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


@click.command()
@click.option('--path', required=True)
@click.option('--output', required=True)
@click.option('--since')
@click.option('--end')
@click.option('--user', multiple=True)
def main(path, output, since, end, user):
    repo = pygit2.Repository(path)
    if since:
        since = resolve_dateref(since, repo)
    if end:
        end = resolve_dateref(end, repo)

    groups = {}
    count = 0
    for commit in repo.walk(
            repo.head.target):
        cdate = commit_date(commit)
        if since and cdate <= since:
            break
        if end and cdate >= end:
            continue
        if user and commit.author.name not in user:
            continue

        parts = commit.message.strip().split('-', 1)
        if not len(parts) > 1:
            print("bad commit %s %s" % (cdate, commit.message))
            category = 'other'
        else:
            category = parts[0]
        category = category.strip().lower()
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

    with open(output, 'w') as fh:
        for k in sorted(groups):
            if k in skip:
                continue
            print("# %s" % k, file=fh)
            for c in sorted(groups[k]):
                print(" - %s" % c.strip(), file=fh)
            print("\n", file=fh)


if __name__ == '__main__':
    main()
