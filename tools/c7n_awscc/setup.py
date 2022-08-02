# Automatically generated from pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_awscc', 'c7n_awscc.resources']

package_data = \
{'': ['*'], 'c7n_awscc': ['data/*']}

install_requires = \
['argcomplete (==2.0.0)',
 'attrs (==22.1.0)',
 'boto3 (==1.24.44)',
 'botocore (==1.27.44)',
 'c7n (==0.9.17)',
 'click==8.1.3; python_version >= "3.7"',
 'colorama==0.4.5; python_version >= "3.7" and python_full_version < "3.0.0" '
 'and platform_system == "Windows" or platform_system == "Windows" and '
 'python_version >= "3.7" and python_full_version >= "3.5.0"',
 'docutils (==0.17.1)',
 'importlib-metadata (==4.12.0)',
 'importlib-metadata==4.12.0; python_version < "3.8" and python_version >= '
 '"3.7"',
 'importlib-resources (==5.9.0)',
 'jmespath (==1.0.1)',
 'jsonpatch==1.32; (python_version >= "2.7" and python_full_version < "3.0.0") '
 'or (python_full_version >= "3.5.0")',
 'jsonpointer==2.3; python_version >= "2.7" and python_full_version < "3.0.0" '
 'or python_full_version >= "3.5.0"',
 'jsonschema (==4.9.0)',
 'pkgutil-resolve-name (==1.3.10)',
 'pyrsistent (==0.18.1)',
 'python-dateutil (==2.8.2)',
 'pyyaml (==6.0)',
 's3transfer (==0.6.0)',
 'six (==1.16.0)',
 'tabulate (==0.8.10)',
 'typing-extensions (==4.3.0)',
 'typing-extensions==4.3.0; python_version < "3.8" and python_version >= "3.7"',
 'urllib3 (==1.26.11)',
 'zipp (==3.8.1)',
 'zipp==3.8.1; python_version < "3.8" and python_version >= "3.7"']

setup_kwargs = {
    'name': 'c7n-awscc',
    'version': '0.1.2',
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
