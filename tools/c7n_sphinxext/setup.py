# Automatically generated from pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_sphinxext']

package_data = \
{'': ['*'], 'c7n_sphinxext': ['_templates/*']}

install_requires = \
['alabaster==0.7.12; python_version >= "3.6" and python_full_version < "3.0.0" '
 'or python_full_version >= "3.4.0" and python_version >= "3.6"',
 'argcomplete (==2.0.0)',
 'attrs (==21.4.0)',
 'attrs==21.4.0; python_version >= "3.6" and python_full_version < "3.0.0" and '
 'python_version < "4.0" or python_version >= "3.6" and python_version < "4.0" '
 'and python_full_version >= "3.5.0"',
 'babel==2.10.3; python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.4.0" and python_version >= "3.6"',
 'boto3 (==1.24.44)',
 'botocore (==1.27.44)',
 'c7n (==0.9.17)',
 'certifi==2022.6.15; python_version >= "3.7" and python_version < "4"',
 'charset-normalizer==2.1.0; python_version >= "3.7" and python_version < "4" '
 'and python_full_version >= "3.6.0"',
 'click==8.1.3; python_version >= "3.7"',
 'colorama==0.4.5; python_version >= "3.7" and python_full_version < "3.0.0" '
 'and sys_platform == "win32" and platform_system == "Windows" and '
 '(python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.4.0" and python_version >= "3.6") or sys_platform '
 '== "win32" and python_version >= "3.7" and python_full_version >= "3.5.0" '
 'and platform_system == "Windows" and (python_version >= "3.6" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.4.0" and '
 'python_version >= "3.6")',
 'commonmark==0.9.1',
 'docutils (==0.17.1)',
 'docutils==0.17.1; (python_version >= "2.7" and python_full_version < '
 '"3.0.0") or (python_full_version >= "3.5.0")',
 'idna==3.3; python_version >= "3.7" and python_version < "4"',
 'imagesize==1.4.1; python_version >= "3.6" and python_full_version < "3.0.0" '
 'or python_full_version >= "3.4.0" and python_version >= "3.6"',
 'importlib-metadata (==4.12.0)',
 'importlib-metadata==4.12.0; python_version < "3.8" and python_version >= '
 '"3.7" and (python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.4.0" and python_version >= "3.6")',
 'importlib-resources (==5.9.0)',
 'jinja2==3.1.2; python_version >= "3.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.4.0" and python_version >= "3.7"',
 'jmespath (==1.0.1)',
 'jsonschema (==4.9.0)',
 'markdown-it-py==1.1.0; python_version >= "3.6" and python_version < "4.0"',
 'markdown==3.0.1; python_version >= "2.7" and python_full_version < "3.0.0" '
 'or python_full_version >= "3.4.0"',
 'markupsafe==2.1.1; python_version >= "3.7"',
 'mdit-py-plugins==0.2.8; python_version >= "3.6" and python_version < "4.0"',
 'myst-parser==0.15.2; python_version >= "3.6"',
 'packaging==21.3; python_version >= "3.6" and python_full_version < "3.0.0" '
 'or python_full_version >= "3.4.0" and python_version >= "3.6"',
 'pkgutil-resolve-name (==1.3.10)',
 'pygments==2.12.0; python_version >= "3.6"',
 'pyparsing==3.0.9; python_full_version >= "3.6.8" and python_version >= "3.6"',
 'pyrsistent (==0.18.1)',
 'python-dateutil (==2.8.2)',
 'pytz==2022.1; python_version >= "3.6"',
 'pyyaml (==6.0)',
 'pyyaml==6.0; python_version >= "3.6"',
 'recommonmark==0.6.0',
 'requests==2.28.1; python_version >= "3.7" and python_version < "4" and '
 '(python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.4.0" and python_version >= "3.6")',
 's3transfer (==0.6.0)',
 'six (==1.16.0)',
 'snowballstemmer==2.2.0; python_version >= "3.6" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.4.0" and python_version >= "3.6"',
 'sphinx-markdown-tables==0.0.12',
 'sphinx-rtd-theme==1.0.0; (python_version >= "2.7" and python_full_version < '
 '"3.0.0") or (python_full_version >= "3.4.0")',
 'sphinx==4.5.0; python_version >= "3.6"',
 'sphinxcontrib-applehelp==1.0.2; python_version >= "3.6" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.4.0" and '
 'python_version >= "3.6"',
 'sphinxcontrib-devhelp==1.0.2; python_version >= "3.6" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.4.0" and '
 'python_version >= "3.6"',
 'sphinxcontrib-htmlhelp==2.0.0; python_version >= "3.6" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.4.0" and '
 'python_version >= "3.6"',
 'sphinxcontrib-jsmath==1.0.1; python_version >= "3.6" and python_full_version '
 '< "3.0.0" or python_full_version >= "3.4.0" and python_version >= "3.6"',
 'sphinxcontrib-qthelp==1.0.3; python_version >= "3.6" and python_full_version '
 '< "3.0.0" or python_full_version >= "3.4.0" and python_version >= "3.6"',
 'sphinxcontrib-serializinghtml==1.1.5; python_version >= "3.6" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.4.0" and '
 'python_version >= "3.6"',
 'tabulate (==0.8.10)',
 'typing-extensions (==4.3.0)',
 'typing-extensions==4.3.0; python_version < "3.8" and python_version >= "3.7"',
 'urllib3 (==1.26.11)',
 'urllib3==1.26.11; python_version >= "3.7" and python_full_version < "3.0.0" '
 'and python_version < "4" or python_full_version >= "3.6.0" and '
 'python_version < "4" and python_version >= "3.7"',
 'zipp (==3.8.1)',
 'zipp==3.8.1; python_version < "3.8" and python_version >= "3.7"']

entry_points = \
{'console_scripts': ['c7n-sphinxext = c7n_sphinxext.docgen:main']}

setup_kwargs = {
    'name': 'c7n-sphinxext',
    'version': '1.1.16',
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
