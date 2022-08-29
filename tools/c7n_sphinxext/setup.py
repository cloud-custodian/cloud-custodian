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
 'argcomplete (>=2.0.0,<3.0.0)',
 'attrs (>=22.1.0,<23.0.0)',
 'boto3 (>=1.24.44,<2.0.0)',
 'botocore (>=1.27.44,<2.0.0)',
 'c7n (>=0.9.18,<0.10.0)',
 'click>=8.0,<9.0',
 'docutils (>=0.17.1,<0.18.0)',
 'docutils>=0.14,<0.18',
 'importlib-metadata (>=4.12.0,<5.0.0)',
 'importlib-resources (>=5.9.0,<6.0.0)',
 'jmespath (>=1.0.1,<2.0.0)',
 'jsonschema (>=4.9.0,<5.0.0)',
 'myst-parser>=0.18.0,<0.19.0',
 'pkgutil-resolve-name (>=1.3.10,<2.0.0)',
 'pyrsistent (>=0.18.1,<0.19.0)',
 'python-dateutil (>=2.8.2,<3.0.0)',
 'pyyaml (>=6.0,<7.0)',
 'recommonmark>=0.6.0,<0.7.0',
 's3transfer (>=0.6.0,<0.7.0)',
 'six (>=1.16.0,<2.0.0)',
 'sphinx-rtd-theme>=1.0.0,<2.0.0',
 'sphinx_markdown_tables>=0.0.12,<0.0.13',
 'tabulate (>=0.8.10,<0.9.0)',
 'typing-extensions (>=4.3.0,<5.0.0)',
 'urllib3 (>=1.26.11,<2.0.0)',
 'zipp (>=3.8.1,<4.0.0)']

entry_points = \
{'console_scripts': ['c7n-sphinxext = c7n_sphinxext.docgen:main']}

setup_kwargs = {
    'name': 'c7n-sphinxext',
    'version': '1.1.17',
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
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
