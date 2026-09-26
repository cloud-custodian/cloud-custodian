# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import datetime
import subprocess
import shutil
import sys

from dateutil import parser, tz

# how old a successful release build may be and still be worth downloading
MAX_BUILD_AGE = datetime.timedelta(hours=48)


def run(command):
    """Run a command, returning its stdout.

    Note we deliberately don't use subprocess.getoutput here: it folds
    stderr into the returned string and discards the exit status, so a
    failing `gh` invocation came back as an unparseable blob of error text.
    """
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout, end='')
        print(result.stderr, end='', file=sys.stderr)
        print('%s exited %d' % (command[0], result.returncode), file=sys.stderr)
        sys.exit(result.returncode)
    return result.stdout


def main():
    gh_bin = shutil.which("gh")
    assert gh_bin, "Please install gh cli https://cli.github.com"
    command = [
        gh_bin,
        "run",
        "list",
        "-w",
        "release.yml",
        "--json",
        "status",
        "--json",
        "workflowName",
        "--json",
        "updatedAt",
        "--json",
        "databaseId",
        "--json",
        "conclusion",
        "--json",
        "headBranch",
        "--json",
        "headSha",
        "--limit",
        "10",
    ]
    artifact_builds = json.loads(run(command))

    now = datetime.datetime.now(tz.tzutc())
    candidate = None

    for build in artifact_builds:
        if not build['conclusion'] == 'success':
            continue
        if not build['headBranch'] == 'main':
            continue
        build_time = parser.parse(build['updatedAt'])
        build_age = now - build_time
        if build_age > MAX_BUILD_AGE:
            continue
        build['age'] = build_age
        candidate = build
        break
    if not candidate:
        print('no release candidate build found')
        sys.exit(1)

    print('found artifact build candidate %s' % candidate)
    command = [gh_bin, "run", "download", str(candidate['databaseId']), "-n", "built-wheels"]
    run(command)
    print('artifacts downloaded')


if __name__ == '__main__':
    main()
