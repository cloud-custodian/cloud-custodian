# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import datetime
import subprocess
import shutil
import sys

from dateutil import parser, tz


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
    output = subprocess.getoutput(" ".join(command))
    artifact_builds = json.loads(output)

    now = datetime.datetime.utcnow().replace(tzinfo=tz.tzutc())
    candidate = None

    for build in artifact_builds:
        if not build['conclusion'] == 'success':
            continue
        if not build['headBranch'] == 'main':
            continue
        build_time = parser.parse(build['updatedAt'])
        build_age = now - build_time
        # only consider builds less then two hours old
        if build_age.total_seconds() > (60 * 60 * 2) * 24:
            continue
        build['age'] = build_age
        candidate = build
        break
    if not candidate:
        print('no release candidate build found')
        sys.exit(1)

    print('found artifact build candidate %s' % candidate)
    command = [gh_bin, "run", "download", str(candidate['databaseId']), "-n", "built-wheels"]
    subprocess.getoutput(" ".join(command))
    print('artifacts downloaded')


if __name__ == '__main__':
    main()
