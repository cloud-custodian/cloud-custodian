# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_kube',
 'c7n_kube.actions',
 'c7n_kube.resources',
 'c7n_kube.resources.apps',
 'c7n_kube.resources.core']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (>=1.12.2,<2.0.0)',
 'attrs (>=20.3.0,<21.0.0)',
 'boto3 (>=1.17.10,<2.0.0)',
 'botocore (>=1.20.10,<2.0.0)',
 'c7n (>=0.9.11,<0.10.0)',
 'importlib-metadata (>=3.4.0,<4.0.0)',
 'jmespath (>=0.10.0,<0.11.0)',
 'jsonpickle (>=1.3,<2.0)',
 'jsonschema (>=3.2.0,<4.0.0)',
 'kubernetes>=10.0.1,<11.0.0',
 'pyrsistent (>=0.17.3,<0.18.0)',
 'python-dateutil (>=2.8.1,<3.0.0)',
 'pyyaml (>=5.4.1,<6.0.0)',
 's3transfer (>=0.3.4,<0.4.0)',
 'six (>=1.15.0,<2.0.0)',
 'tabulate (>=0.8.8,<0.9.0)',
 'typing-extensions (>=3.7.4.3,<4.0.0.0)',
 'urllib3 (>=1.26.3,<2.0.0)',
 'zipp (>=3.4.0,<4.0.0)']

setup_kwargs = {
    'name': 'c7n-kube',
    'version': '0.2.10',
    'description': 'Cloud Custodian - Kubernetes Provider',
    'long_description': '# Custodian Kubernetes Support\n\n\nWork in Progress - Not Ready For Use.\n\n',
    'long_description_content_type': 'text/markdown',
    'author': 'Cloud Custodian Project',
    'author_email': None,
    'maintainer': None,
    'maintainer_email': None,
    'url': 'https://cloudcustodian.io',
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.6,<4.0',
}


setup(**setup_kwargs)
