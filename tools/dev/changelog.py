# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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


@click.command()
@click.option('--path', required=True)
@click.option('--output', required=True)
@click.option('--since')
def main(path, output, since):
    repo = pygit2.Repository(path)
    if since:
        try:
            since = repo.lookup_reference('refs/tags/%s' % since)
        except KeyError:
            since = parse_date(since).astimezone(tzutc())
        else:
            since = commit_date(since.peel())

    groups = {}
    count = 0
    for commit in repo.walk(
            repo.head.target):

        cdate = commit_date(commit)
        if cdate <= since:
            break
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
