# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_org']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (>=1.12.2,<2.0.0)',
 'attrs (>=20.3.0,<21.0.0)',
 'boto3 (>=1.17.10,<2.0.0)',
 'botocore (>=1.20.10,<2.0.0)',
 'c7n (>=0.9.11,<0.10.0)',
 'click>=7.0,<8.0',
 'importlib-metadata (>=3.4.0,<4.0.0)',
 'jmespath (>=0.10.0,<0.11.0)',
 'jsonpickle (>=1.3,<2.0)',
 'jsonschema (>=3.2.0,<4.0.0)',
 'pyrsistent (>=0.17.3,<0.18.0)',
 'python-dateutil (>=2.8.1,<3.0.0)',
 'pyyaml (>=5.4.1,<6.0.0)',
 's3transfer (>=0.3.4,<0.4.0)',
 'six (>=1.15.0,<2.0.0)',
 'tabulate (>=0.8.8,<0.9.0)',
 'typing-extensions (>=3.7.4.3,<4.0.0.0)',
 'urllib3 (>=1.26.3,<2.0.0)',
 'zipp (>=3.4.0,<4.0.0)']

entry_points = \
{'console_scripts': ['c7n-org = c7n_org.cli:cli']}

setup_kwargs = {
    'name': 'c7n-org',
    'version': '0.6.10',
    'description': 'Cloud Custodian - Parallel Execution',
    'long_description': '# c7n-org: Multi Account Custodian Execution\n\n[//]: # (         !!! IMPORTANT !!!                    )\n[//]: # (This file is moved during document generation.)\n[//]: # (Only edit the original document at ./tools/c7n_org/README.md)\n\nc7n-org is a tool to run custodian against multiple AWS accounts,\nAzure subscriptions, or GCP projects in parallel.\n\n## Installation\n\n```shell\npip install c7n-org\n```\n\nc7n-org has 3 run modes:\n\n```shell\nUsage: c7n-org [OPTIONS] COMMAND [ARGS]...\n\n  custodian organization multi-account runner.\n\nOptions:\n  --help  Show this message and exit.\n\nCommands:\n  report      report on an AWS cross account policy execution\n  run         run a custodian policy across accounts (AWS, Azure, GCP)\n  run-script  run a script across AWS accounts\n```\n\nIn order to run c7n-org against multiple accounts, a config file must\nfirst be created containing pertinent information about the accounts:\n\n\nExample AWS Config File:\n\n```yaml\naccounts:\n- account_id: \'123123123123\'\n  name: account-1\n  regions:\n  - us-east-1\n  - us-west-2\n  role: arn:aws:iam::123123123123:role/CloudCustodian\n  vars:\n    charge_code: xyz\n  tags:\n  - type:prod\n  - division:some division\n  - partition:us\n  - scope:pci\n...\n```\n\nExample Azure Config File:\n\n```yaml\nsubscriptions:\n- name: Subscription-1\n  subscription_id: a1b2c3d4-e5f6-g7h8i9...\n- name: Subscription-2\n  subscription_id: 1z2y3x4w-5v6u-7t8s9r...\n```\n\nExample GCP Config File:\n\n```yaml\nprojects:\n- name: app-dev\n  project_id: app-203501\n  tags:\n  - label:env:dev  \n- name: app-prod\n  project_id: app-1291\n  tags:\n  - label:env:dev\n\n```\n\n### Config File Generation\n\nWe also distribute scripts to generate the necessary config file in the `scripts` folder.\n\n**Note** Currently these are distributed only via git, per\nhttps://github.com/cloud-custodian/cloud-custodian/issues/2420 we\'ll\nbe looking to incorporate them into a new c7n-org subcommand.\n\n- For **AWS**, the script `orgaccounts.py` generates a config file\n  from the AWS Organizations API\n\n- For **Azure**, the script `azuresubs.py` generates a config file\n  from the Azure Resource Management API\n\n    - Please see the [Additional Azure Instructions](#Additional-Azure-Instructions)\n    - for initial setup and other important info\n\n- For **GCP**, the script `gcpprojects.py` generates a config file from\n  the GCP Resource Management API\n\n\n```shell\npython orgaccounts.py -f accounts.yml\n```\n```shell\npython azuresubs.py -f subscriptions.yml\n```\n```shell\npython gcpprojects.py -f projects.yml\n```\n\n## Running a Policy with c7n-org\n\nTo run a policy, the following arguments must be passed in:\n\n```shell\n-c | accounts|projects|subscriptions config file\n-s | output directory\n-u | policy\n```\n\n\n```shell\nc7n-org run -c accounts.yml -s output -u test.yml --dryrun\n```\n\nAfter running the above command, the following folder structure will be created:\n\n```\noutput\n    |_ account-1\n        |_ us-east-1\n            |_ policy-name\n                |_ resources.json\n                |_ custodian-run.log\n        |_ us-west-2\n            |_ policy-name\n                |_ resources.json\n                |_ custodian-run.log\n    |- account-2\n...\n```\n\nUse `c7n-org report` to generate a csv report from the output directory.\n\n## Selecting accounts, regions, policies for execution\n\nYou can filter the accounts to be run against by either passing the\naccount name or id via the `-a` flag, which can be specified multiple\ntimes, or alternatively with comma separated values.\n\nGroups of accounts can also be selected for execution by specifying\nthe `-t` tag filter.  Account tags are specified in the config\nfile. ie given the above accounts config file you can specify all prod\naccounts with `-t type:prod`. you can specify the -t flag multiple\ntimes or use a comma separated list.\n\nYou can specify which policies to use for execution by either\nspecifying `-p` or selecting groups of policies via their tags with\n`-l`, both options support being specified multiple times or using\ncomma separated values.\n\nBy default in aws, c7n-org will execute in parallel across regions,\nthe \'-r\' flag can be specified multiple times, and defaults to\n(us-east-1, us-west-2).  a special value of `all` will execute across\nall regions.\n\n\nSee `c7n-org run --help` for more information.\n\n## Defining and using variables\n\nEach account/subscription/project configuration in the config file can\nalso define a variables section `vars` that can be used in policies\'\ndefinitions and are interpolated at execution time. These are in\naddition to the default runtime variables custodian provides like\n`account_id`, `now`, and `region`.\n\nExample of defining in c7n-org config file:\n\n```yaml\naccounts:\n- account_id: \'123123123123\'\n  name: account-1\n  role: arn:aws:iam::123123123123:role/CloudCustodian\n  vars:\n    charge_code: xyz\n```\n\nExample of using in a policy file:\n\n```yaml\npolicies:\n - name: ec2-check-tag\n   resource: aws.ec2\n   filters:\n      - "tag:CostCenter": "{charge_code}"\n```\n\n**Note** Variable interpolation is sensitive to proper quoting and spacing,\ni.e., `{ charge_code }` would be invalid due to the extra white space. Additionally,\nyaml parsing can transform a value like `{charge_code}` to null, unless it\'s quoted\nin strings like the above example. Values that do interpolation into other content\ndon\'t require quoting, i.e., "my_{charge_code}".\n\n## Other commands\n\nc7n-org also supports running arbitrary scripts against accounts via the run-script command.\nFor AWS the standard AWS SDK credential information is exported into the process environment before executing.\nFor Azure and GCP, only the environment variables `AZURE_SUBSCRIPTION_ID` and `PROJECT_ID` are exported(in addition\nof the system env variables).\n\nc7n-org also supports generating reports for a given policy execution\nacross accounts via the `c7n-org report` subcommand.\n\n## Additional Azure Instructions\n\nIf you\'re using an Azure Service Principal for executing c7n-org\nyou\'ll need to ensure that the principal has access to multiple\nsubscriptions.\n\nFor instructions on creating a service principal and granting access\nacross subscriptions, visit the [Azure authentication docs\npage](https://cloudcustodian.io/docs/azure/authentication.html).\n',
    'long_description_content_type': 'text/markdown',
    'author': 'Cloud Custodian Project',
    'author_email': None,
    'maintainer': None,
    'maintainer_email': None,
    'url': 'https://cloudcustodian.io',
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'entry_points': entry_points,
    'python_requires': '>=3.6,<4.0',
}


setup(**setup_kwargs)
