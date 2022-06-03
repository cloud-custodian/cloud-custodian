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
 'attrs (>=21.4.0,<22.0.0)',
 'boto3 (>=1.21.42,<2.0.0)',
 'botocore (>=1.24.42,<2.0.0)',
 'c7n (>=0.9.16,<0.10.0)',
 'click>=8.0,<9.0',
 'docutils (>=0.17.1,<0.18.0)',
 'importlib-metadata (>=4.11.3,<5.0.0)',
 'importlib-resources (>=5.7.1,<6.0.0)',
 'jmespath (>=1.0.0,<2.0.0)',
 'jsonpatch>=1.32,<2.0',
 'jsonschema (>=4.4.0,<5.0.0)',
 'pyrsistent (>=0.18.1,<0.19.0)',
 'python-dateutil (>=2.8.2,<3.0.0)',
 'pyyaml (>=6.0,<7.0)',
 's3transfer (>=0.5.2,<0.6.0)',
 'six (>=1.16.0,<2.0.0)',
 'tabulate (>=0.8.9,<0.9.0)',
 'typing-extensions (>=4.2.0,<5.0.0)',
 'urllib3 (>=1.26.9,<2.0.0)',
 'zipp (>=3.8.0,<4.0.0)']

setup_kwargs = {
    'name': 'c7n-awscc',
    'version': '0.1.1',
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
