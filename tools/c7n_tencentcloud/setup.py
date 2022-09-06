# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_tencentcloud',
 'c7n_tencentcloud.actions',
 'c7n_tencentcloud.filters',
 'c7n_tencentcloud.resources']

package_data = \
{'': ['*']}

install_requires = \
['tencentcloud-sdk-python>=3.0.715,<4.0.0']

setup_kwargs = {
    'name': 'c7n-tencentcloud',
    'version': '0.1.0',
    'description': 'Cloud Custodian - Tencent Cloud Provider',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': None,
    'long_description_content_type': 'text/markdown',
    'author': 'Tencent Cloud',
    'author_email': None,
    'maintainer': None,
    'maintainer_email': None,
    'url': None,
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.9,<4.0',
}


setup(**setup_kwargs)
