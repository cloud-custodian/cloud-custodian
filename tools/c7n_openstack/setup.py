# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = [
    'c7n_openstack',
    'c7n_openstack.resources'
]

package_data = {'': ['*']}

install_requires = \
['openstacksdk (>=0.52.0)',
 'c7n (>=0.9.8,<0.10.0)']


setup_kwargs = {
    'name': 'c7n-openstack',
    'version': '0.0.1',
    'description': 'Cloud Custodian - OpenStack Provider',
    'long_description': '# Custodian OpenStack Support',
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
