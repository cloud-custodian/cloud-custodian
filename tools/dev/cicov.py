#!/usr/bin/env python2

import subprocess
import os
import logging

log = logging.getLogger('cicov')

# https://docs.microsoft.com/en-us/azure/devops/pipelines/build/variables?view=vsts

config = {
    'branch': os.environ.get('BUILD_BRANCH'),
    'pr': os.environ.get('PR'),
    'build': os.environ.get('BUILD_ID'),
    'commit': os.environ.get('BUILD_COMMIT')}


def main():
    logging.basicConfig(level=logging.INFO)

    for k in ('BUILD_BRANCH', 'PR', 'BUILD_ID', 'BUILD_COMMIT', 'COMMIT', 'BRANCH'):
        v = os.environ.get(k)
        log.info("Env var %s=%s" % (k, v))

    args = ['codecov']
    for k, v in config.items():
        if not v:
            continue
        # value not set
        if 'system.pullRequest' in v:
            continue
        args.append("--%s" % k)
        args.append(v)
    log.info("Uploading CodeCoverage: %r" % (' '.join(args)))
    subprocess.check_call(args)


if __name__ == '__main__':
    main()

