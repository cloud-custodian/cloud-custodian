# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_awscc', 'c7n_awscc.resources']

package_data = \
{'': ['*'], 'c7n_awscc': ['data/*']}

install_requires = \
['argcomplete (>=2.0.0,<3.0.0)',
 'attrs (>=22.2.0,<23.0.0)',
 'boto3 (>=1.26.50,<2.0.0)',
 'botocore (>=1.29.50,<2.0.0)',
 'c7n (>=0.9.22,<0.10.0)',
 'click>=8.0,<9.0',
 'docutils (>=0.17.1,<0.18.0)',
 'importlib-metadata (>=4.13.0,<5.0.0)',
 'importlib-resources (>=5.10.2,<6.0.0)',
 'jmespath (>=1.0.1,<2.0.0)',
 'jsonpatch>=1.32,<2.0',
 'jsonschema (>=4.17.3,<5.0.0)',
 'pkgutil-resolve-name (>=1.3.10,<2.0.0)',
 'pyrsistent (>=0.19.3,<0.20.0)',
 'python-dateutil (>=2.8.2,<3.0.0)',
 'pyyaml (>=6.0,<7.0)',
 's3transfer (>=0.6.0,<0.7.0)',
 'six (>=1.16.0,<2.0.0)',
 'tabulate (>=0.8.10,<0.9.0)',
 'typing-extensions (>=4.4.0,<5.0.0)',
 'urllib3 (>=1.26.14,<2.0.0)',
 'zipp (>=3.11.0,<4.0.0)']

setup_kwargs = {
    'name': 'c7n-awscc',
    'version': '0.1.7',
    'description': 'Cloud Custodian - AWS Cloud Control Provider',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': '\n# Custodian AWS Cloud Control Provider\n\n\n',
    'long_description_content_type': 'text/markdown',
    'author': 'Cloud Custodian Project',
    'author_email': 'cloud-custodian@googlegroups.com',
    'project_urls': {
       'Homepage': 'https://cloudcustodian.io',
       'Documentation': 'https://cloudcustodian.io/docs/',
       'Source': 'https://github.com/cloud-custodian/cloud-custodian',
       'Issue Tracker': 'https://github.com/cloud-custodian/cloud-custodian/issues',
    },
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
