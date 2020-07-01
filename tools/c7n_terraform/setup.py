# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_terraform']

package_data = \
{'': ['*']}

install_requires = \
['click>=7.1.2,<8.0.0', 'python-hcl2>=0.2.6,<0.3.0', 'rich>=1.1.9,<2.0.0']

setup_kwargs = {
    'name': 'c7n-terraform',
    'version': '0.1.0',
    'description': 'Cloud Custodian Provider for evaluating Terraform',
    'long_description': None,
    'long_description_content_type': 'text/markdown',
    'author': 'Kapil Thangavelu',
    'author_email': 'kapilt@gmail.com',
    'maintainer': None,
    'maintainer_email': None,
    'url': None,
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
