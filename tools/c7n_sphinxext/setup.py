# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_sphinxext']

package_data = \
{'': ['*'], 'c7n_sphinxext': ['_templates/*']}

install_requires = \
['Pygments>=2.6.1,<3.0.0',
 'Sphinx>=3.0,<3.1',
 'argcomplete (>=1.11.1,<2.0.0)',
 'attrs (>=19.3.0,<20.0.0)',
 'boto3 (>=1.14.16,<2.0.0)',
 'botocore (>=1.17.16,<2.0.0)',
 'c7n (>=0.9.4,<0.10.0)',
 'docutils (>=0.15.2,<0.16.0)',
 'importlib-metadata (>=1.7.0,<2.0.0)',
 'jmespath (>=0.10.0,<0.11.0)',
 'jsonschema (>=3.2.0,<4.0.0)',
 'pyrsistent (>=0.16.0,<0.17.0)',
 'python-dateutil (>=2.8.1,<3.0.0)',
 'pyyaml (>=5.3.1,<6.0.0)',
 'recommonmark>=0.6.0,<0.7.0',
 's3transfer (>=0.3.3,<0.4.0)',
 'six (>=1.15.0,<2.0.0)',
 'sphinx_markdown_tables>=0.0.12,<0.0.13',
 'sphinx_rtd_theme>=0.4.3,<0.5.0',
 'tabulate (>=0.8.7,<0.9.0)',
 'urllib3 (>=1.25.9,<2.0.0)',
 'zipp (>=3.1.0,<4.0.0)']

entry_points = \
{'console_scripts': ['c7n-sphinxext = c7n_sphinxext.docgen:main']}

setup_kwargs = {
    'name': 'c7n-sphinxext',
    'version': '1.1.3',
    'description': 'Cloud Custodian - Sphinx Extensions',
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
