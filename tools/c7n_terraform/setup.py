# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_terraform']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (>=2.0.0,<3.0.0)',
 'attrs (>=22.1.0,<23.0.0)',
 'boto3 (>=1.24.44,<2.0.0)',
 'botocore (>=1.27.44,<2.0.0)',
 'c7n (>=0.9.18,<0.10.0)',
 'click>=8.0,<9.0',
 'docutils (>=0.17.1,<0.18.0)',
 'importlib-metadata (>=4.12.0,<5.0.0)',
 'importlib-resources (>=5.9.0,<6.0.0)',
 'jmespath (>=1.0.1,<2.0.0)',
 'jsonschema (>=4.9.0,<5.0.0)',
 'pkgutil-resolve-name (>=1.3.10,<2.0.0)',
 'pyrsistent (>=0.18.1,<0.19.0)',
 'python-dateutil (>=2.8.2,<3.0.0)',
 'python-hcl2>=2.0,<3.0',
 'pyyaml (>=6.0,<7.0)',
 's3transfer (>=0.6.0,<0.7.0)',
 'six (>=1.16.0,<2.0.0)',
 'tabulate (>=0.8.10,<0.9.0)',
 'typing-extensions (>=4.3.0,<5.0.0)',
 'urllib3 (>=1.26.11,<2.0.0)',
 'zipp (>=3.8.1,<4.0.0)']

setup_kwargs = {
    'name': 'c7n-terraform',
    'version': '0.1.8',
    'description': 'Cloud Custodian Provider for evaluating Terraform',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': "\n# Cloud Custodian Terraform Provider\n\nCustodian's terraform provider enables writing and evaluating\ncustodian policies against Terraform IaaC modules.\n\n\ntldr: we want to enable writing custodian policies against IaaC assets (terraform, cfn, etc) directly in devops/ci pipelines.\n\n# Purpose\n\nThe primary purpose of this is to integrate with ci/cd pipelines to\nevaluate compliance and governance early in the deployment\nlifecycle. Custodian cloud providers provide for realtime detection\nand remediation as a detective control against infrastructure already\ndeployed in the environment regardless of how it was provisioned. As\nan initial target, the terraform provider is designed to complement\nthat with preventive enforcement earlier in the\nlifecycle. ie. enabling a shift-left to policy enforcement.\n\n\n# Pipeline CLI\n\nIn looking at expanding out to shift-left pipeline use cases, one\nthing that becomes clearer is that custodian's default cli ux isn't\nperhaps the best fit for the target audience. When we're operating\nagainst cloud resources we have to deal with cardinalities in the\nthousands to millions. When we're operating in the pipelines we're\ntypically dealing with resource cardinalities in the 10s. Additionally\nthere is a goal expectation of having rich output that correlates to\nthe ci tooling (github annotations, etc) or pinpointing the issue for\na developer, as well as color'd output and other niceties. we could\nincorporate that as a new subcommand into the main custodian cli\n(dependent on presence of iaac providers installed), or have a\ndedicated subcommand associated.\n\nThe other main deficiency with the cli is that we're not able to pass\ndirectly the iaac files as data sets we want to consider. Typically\npolicies have expressed this as query parameterization within the\npolicy as being able to specify the exact target set. But the use case\nhere is more typically command line driven with specification of both\npolicy files and target IaaC files, as well as other possible vcs\nintegrations (policystream style wrt delta files) or ci integrations.\n\n# Resources\n\nwrt to the iaac provider we can either operate loosely typed or strongly typed. with strong typing we can spec out exact attributes and potentially do additional possibly validation wrt to user specified attributes, but it requires keeping an up to date store of all iaac provider assets, which could be both fairly large and rapidly changing (terraform has over 150 providers all release independently). for now, I think it would be good to keep to loose typing on resources. .. and perhaps document provider addressable resource attributes  as part of documentation.\n\nLoose typing would enable working out of the box with extant providers, but policy authors would have to consult reference docs for their respective providers on available attributes or even provider resource type existence. From a custodian perspective we would use a common resource implementation across provider resource types.\n\n#  Examples\n\n```yaml\n- resource: terraform.aws_dynamodb_table\n   name: ensure encryption\n   filters:\n      server_side_encryption.enabled: true\n      kms_key_arn: key_alias\n```\n\n\n\n# \n\n  custodian run terraform.yml\n  \n  custodian report --format=\n  \n# dedicated cli\n\n\n  custodian run-source terraform.yml\n",
    'long_description_content_type': 'text/markdown',
    'author': 'Cloud Custodian Project',
    'author_email': None,
    'maintainer': None,
    'maintainer_email': None,
    'url': 'https://cloudcustodian.io',
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
