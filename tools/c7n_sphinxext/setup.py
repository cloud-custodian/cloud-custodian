# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_sphinxext']

package_data = \
{'': ['*'], 'c7n_sphinxext': ['_templates/*']}

install_requires = \
['Pygments>=2.10.0,<3.0.0',
 'Sphinx>=4.2.0,<5.0.0',
 'argcomplete (>=1.12.3,<2.0.0)',
 'attrs (>=21.2.0,<22.0.0)',
 'boto3 (>=1.19.12,<2.0.0)',
 'botocore (>=1.22.12,<2.0.0)',
 'c7n (>=0.9.14,<0.10.0)',
 'click>=8.0,<9.0',
 'docutils (>=0.17.1,<0.18.0)',
 'docutils>=0.14,<0.18',
 'importlib-metadata (>=4.8.1,<5.0.0)',
 'jmespath (>=0.10.0,<0.11.0)',
 'jsonschema (>=3.2.0,<4.0.0)',
 'myst-parser>=0.15.2,<0.16.0',
 'pyrsistent (>=0.18.0,<0.19.0)',
 'python-dateutil (>=2.8.2,<3.0.0)',
 'pyyaml (>=5.4.1,<6.0.0)',
 'recommonmark>=0.6.0,<0.7.0',
 's3transfer (>=0.5.0,<0.6.0)',
 'six (>=1.16.0,<2.0.0)',
 'sphinx-rtd-theme>=1.0.0,<2.0.0',
 'sphinx_markdown_tables>=0.0.12,<0.0.13',
 'tabulate (>=0.8.9,<0.9.0)',
 'typing-extensions (>=3.10.0.2,<4.0.0.0)',
 'typing-extensions>=3.7.4,<4.0.0',
 'urllib3 (>=1.26.7,<2.0.0)',
 'zipp (>=3.6.0,<4.0.0)']

entry_points = \
{'console_scripts': ['c7n-sphinxext = c7n_sphinxext.docgen:main']}

setup_kwargs = {
    'name': 'c7n-sphinxext',
    'version': '1.1.13',
    'description': 'Cloud Custodian - Sphinx Extensions',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': '# Sphinx Extensions\n\nCustom sphinx extensions for use with Cloud Custodian.\n\n',
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
