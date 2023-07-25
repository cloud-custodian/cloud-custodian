# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
CodeArtifact does a best practice around immutable versions in


for purposes of staging and testing a release, we do want to be able to
verify the same release after updates/packaging fixes. to do so we
delete the current package version from the repo.

"""
import boto3
import os
import tomllib
from pathlib import Path


def main():
    makefile = (Path('.') / "Makefile").read_text().splitlines()

    package_set = False
    for l in makefile:
        if l.startswith('PKG_SET'):
            package_set = l.split('=', 1)[-1].strip().split(' ')
            break

    package_versions = {}
    package_manifests = [
        Path('.') / 'pyproject.toml',
        Path('.') / "tools" / "c7n_left" / "pyproject.toml"
    ]
    package_manifests.extend([Path(f'{pkg}/pyproject.toml') for pkg in package_set])

    for p in package_manifests:
        content = tomllib.loads(p.read_text())
        pkg_info = content['tool']['poetry']
        package_versions[pkg_info['name']] = pkg_info['version']

    client = boto3.client('codeartifact')

    pkg_domain = os.environ['PKG_DOMAIN']
    pkg_repo = os.environ['PKG_REPO']

    print('Cleaning out package versions from staging repo')

    for pkg, version in package_versions.items():
        print(f'remove {pkg} {version}')
        client.delete_package_versions(
            domain=pkg_domain,
            repository=pkg_repo,
            package=pkg,
            versions=[version],
            format='pypi',
        )


if __name__ == '__main__':
    main()
