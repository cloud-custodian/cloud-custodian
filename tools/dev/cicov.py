#!/usr/bin/env python2

import subprocess
import os
import logging

log = logging.getLogger('cicov')

# https://docs.microsoft.com/en-us/azure/devops/pipelines/build/variables?view=vsts


config = {
    'branch': os.environ.get('BRANCH'),
    'pr': os.environ.get('PR'),
    'build': os.environ.get('BUILD_ID'),
    'commit': os.environ.get('BUILD_COMMIT')}

UNSET = "system.pullRequest"


def main():
    logging.basicConfig(level=logging.INFO)

    # Foresenics on the variables set in a context
    for k in ('BUILD_BRANCH', 'PR', 'BUILD_ID', 'BUILD_COMMIT', 'COMMIT', 'BRANCH'):
        v = os.environ.get(k)
        log.info("Env var %s=%s" % (k, v))

    # Defer to pull request branch (system.pullRequest), if thats not set
    # then use Build.SourceBranchName
    if UNSET in config['branch']:
        config['branch'] = os.environ['BUILD_BRANCH']

    args = ['codecov']
    # Assemble cli args, skip all unset values.
    for k, v in config.items():
        if not v:
            continue
        # value not set
        if UNSET in v:
            continue
        args.append("--%s" % k)
        args.append(v)
    log.info("Uploading CodeCoverage: %r" % (' '.join(args)))
    subprocess.check_call(args)


if __name__ == '__main__':
    main()
