# Automatically generated from pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

modules = \
['policystream']
install_requires = \
['argcomplete (==2.0.0)',
 'attrs (==22.1.0)',
 'boto3 (==1.24.44)',
 'boto3==1.24.44; python_version >= "3.7"',
 'botocore (==1.27.44)',
 'botocore==1.27.44; python_version >= "3.7"',
 'c7n (==0.9.17)',
 'cached-property==1.5.2; python_version < "3.8" and python_version >= "3.7"',
 'certifi==2022.6.15; python_version >= "3.7" and python_version < "4"',
 'cffi==1.15.1; python_version >= "3.7"',
 'charset-normalizer==2.1.0; python_version >= "3.7" and python_version < "4" '
 'and python_full_version >= "3.6.0"',
 'click==8.1.3; python_version >= "3.7"',
 'colorama==0.4.5; python_version >= "3.7" and python_full_version < "3.0.0" '
 'and platform_system == "Windows" or platform_system == "Windows" and '
 'python_version >= "3.7" and python_full_version >= "3.5.0"',
 'docutils (==0.17.1)',
 'idna==3.3; python_version >= "3.7" and python_version < "4"',
 'importlib-metadata (==4.12.0)',
 'importlib-metadata==4.12.0; python_version < "3.8" and python_version >= '
 '"3.7"',
 'importlib-resources (==5.9.0)',
 'jmespath (==1.0.1)',
 'jmespath==1.0.1; python_version >= "3.7"',
 'jsonschema (==4.9.0)',
 'pkgutil-resolve-name (==1.3.10)',
 'pycparser==2.21; python_version >= "3.7" and python_full_version < "3.0.0" '
 'or python_full_version >= "3.4.0" and python_version >= "3.7"',
 'pygit2==1.9.2; python_version >= "3.7"',
 'pyrsistent (==0.18.1)',
 'python-dateutil (==2.8.2)',
 'python-dateutil==2.8.2; python_version >= "3.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.3.0" and python_version >= "3.7"',
 'pyyaml (==6.0)',
 'pyyaml==6.0; python_version >= "3.6"',
 'requests==2.28.1; python_version >= "3.7" and python_version < "4"',
 's3transfer (==0.6.0)',
 's3transfer==0.6.0; python_version >= "3.7"',
 'six (==1.16.0)',
 'six==1.16.0; python_version >= "3.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.3.0" and python_version >= "3.7"',
 'tabulate (==0.8.10)',
 'typing-extensions (==4.3.0)',
 'typing-extensions==4.3.0; python_version < "3.8" and python_version >= "3.7"',
 'urllib3 (==1.26.11)',
 'urllib3==1.26.11; python_version >= "3.7" and python_full_version < "3.0.0" '
 'and python_version < "4" or python_full_version >= "3.6.0" and '
 'python_version < "4" and python_version >= "3.7"',
 'zipp (==3.8.1)',
 'zipp==3.8.1; python_version < "3.8" and python_version >= "3.7"']

entry_points = \
{'console_scripts': ['c7n-policystream = policystream:cli']}

setup_kwargs = {
    'name': 'c7n-policystream',
    'version': '0.4.16',
    'description': 'Cloud Custodian - Git Commits as Logical Policy Changes',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': '# c7n-policystream: Policy Changes from Git\n\n% [comment]: # (         !!! IMPORTANT !!!                    )\n% [comment]: # (This file is moved during document generation.)\n% [comment]: # (Only edit the original document at ./tools/c7n_policystream/README.md)\n\nUsing custodian in accordance with infrastructure as code principles,\nwe store policy assets in a versioned control repository. This\nprovides for an audit log and facilitates code reviews. However this\ncapability is primarily of use to humans making semantic interpretations\nof changes.\n\nThis script also provides logical custodian policy changes over a git\nrepo and allows streaming those changes for machine readable/application\nconsumption. Its typically used as a basis for CI integrations or indexes\nover policies.\n\nTwo example use cases:\n\n  - Doing dryrun only on changed policies within a pull request\n  - Constructing a database of policy changes.\n\nPolicystream works on individual github repositories, or per Github integration\nacross an organization\'s set of repositories.\n\n## Install\n\npolicystream can be installed via pypi, provided the require pre-requisites\nlibraries are available (libgit2 > 0.26)\n\n```\npip install c7n-policystream\n```\n\nDocker images available soon, see build for constructing your own.\n\n## Build\n\nAlternatively a docker image can be built as follows\n\n```shell\n# Note must be top level directory of checkout\ncd cloud-custodian\n\ndocker build -t policystream:latest -f tools/c7n_policystream/Dockerfile .\n\ndocker run --mount src="$(pwd)",target=/repos,type=bind policystream:latest\n```\n\n## Usage\n\nStreaming use case (default stream is to stdout, also supports kinesis, rdbms and sqs)\n\n```\n  $ c7n-policystream stream -r foo\n  2018-08-12 12:37:00,567: c7n.policystream:INFO Cloning repository: foo\n  <policy-add policy:foi provider:aws resource:ec2 date:2018-08-02T15:13:28-07:00 author:Kapil commit:09cb85>\n  <policy-moved policy:foi provider:aws resource:ec2 date:2018-08-02T15:14:24-07:00 author:Kapil commit:76fce7>\n  <policy-remove policy:foi provider:aws resource:ec2 date:2018-08-02T15:14:46-07:00 author:Kapil commit:570ca4>\n  <policy-add policy:ec2-guard-duty provider:aws resource:ec2 date:2018-08-02T15:14:46-07:00 author:Kapil commit:570ca4>\n  <policy-add policy:ec2-run provider:aws resource:ec2 date:2018-08-02T15:16:00-07:00 author:Kapil commit:d3d8d4>\n  <policy-remove policy:ec2-run provider:aws resource:ec2 date:2018-08-02T15:18:31-07:00 author:Kapil commit:922c1a>\n  <policy-modified policy:ec2-guard-duty provider:aws resource:ec2 date:2018-08-12T09:39:43-04:00 author:Kapil commit:189ea1>\n  2018-08-12 12:37:01,275: c7n.policystream:INFO Streamed 7 policy changes\n```\n\nPolicy diff between two source and target revision specs. If source\nand target are not specified default revision selection is dependent\non current working tree branch. The intent is for two use cases, if on\na non-master branch then show the diff to master.  If on master show\nthe diff to previous commit on master. For repositories not using the\n`master` convention, please specify explicit source and target.\n\n\n```\n  $ c7n-policystream diff -r foo -v\n```\n\nPull request use, output policies changes between current branch and master.\n\n```\n  $ c7n-policystream diff -r foo\n  policies:\n  - filters:\n    - {type: cross-account}\n    name: lambda-access-check\n    resource: aws.lambda\n```\n\n## Options\n\n```\n$ c7n-policystream --help\nUsage: c7n-policystream [OPTIONS] COMMAND [ARGS]...\n\n  Policy changes from git history\n\nOptions:\n  --help  Show this message and exit.\n\nCommands:\n  diff          Policy diff between two arbitrary revisions.\n  org-checkout  Checkout repositories from a GitHub organization.\n  org-stream    Stream changes for repos in a GitHub organization.\n  stream        Stream git history policy changes to destination.\n```\n',
    'long_description_content_type': 'text/markdown',
    'author': 'Cloud Custodian Project',
    'author_email': None,
    'maintainer': None,
    'maintainer_email': None,
    'url': 'https://cloudcustodian.io',
    'py_modules': modules,
    'install_requires': install_requires,
    'entry_points': entry_points,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
