# Automatically generated from pyproject.toml
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
['argcomplete (==2.0.0)',
 'attrs (==22.1.0)',
 'boto3 (==1.24.44)',
 'botocore (==1.27.44)',
 'c7n (==0.9.17)',
 'cachetools==5.2.0; python_version >= "3.7" and python_version < "4.0" and '
 '(python_version >= "2.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0")',
 'certifi==2022.6.15; python_version >= "3.7" and python_version < "4"',
 'charset-normalizer==2.1.0; python_version >= "3.7" and python_version < "4" '
 'and python_full_version >= "3.6.0"',
 'docutils (==0.17.1)',
 'google-auth==2.9.1; python_version >= "2.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.6.0"',
 'idna==3.3; python_version >= "3.7" and python_version < "4"',
 'importlib-metadata (==4.12.0)',
 'importlib-resources (==5.9.0)',
 'jmespath (==1.0.1)',
 'jsonschema (==4.9.0)',
 'kubernetes==10.0.1',
 'oauthlib==3.2.0; python_version >= "3.6" and python_full_version < "3.0.0" '
 'or python_full_version >= "3.4.0" and python_version >= "3.6"',
 'pkgutil-resolve-name (==1.3.10)',
 'pyasn1-modules==0.2.8; python_version >= "2.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.6.0"',
 'pyasn1==0.4.8; python_version >= "3.6" and python_full_version < "3.0.0" and '
 'python_version < "4" and (python_version >= "3.6" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.6.0" and python_version >= "3.6") or '
 'python_version >= "3.6" and python_version < "4" and (python_version >= '
 '"3.6" and python_full_version < "3.0.0" or python_full_version >= "3.6.0" '
 'and python_version >= "3.6") and python_full_version >= "3.6.0"',
 'pyrsistent (==0.18.1)',
 'python-dateutil (==2.8.2)',
 'python-dateutil==2.8.2; python_version >= "2.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.3.0"',
 'pyyaml (==6.0)',
 'pyyaml==6.0; python_version >= "3.6"',
 'requests-oauthlib==1.3.1; python_version >= "2.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.4.0"',
 'requests==2.28.1; python_version >= "3.7" and python_version < "4" and '
 '(python_version >= "2.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.4.0")',
 'rsa==4.9; python_version >= "3.6" and python_version < "4" and '
 '(python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version >= "3.6")',
 's3transfer (==0.6.0)',
 'six (==1.16.0)',
 'six==1.16.0; python_version >= "2.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0"',
 'tabulate (==0.8.10)',
 'typing-extensions (==4.3.0)',
 'urllib3 (==1.26.11)',
 'urllib3==1.26.11; python_version >= "3.7" and python_full_version < "3.0.0" '
 'and python_version < "4" or python_full_version >= "3.6.0" and '
 'python_version < "4" and python_version >= "3.7"',
 'websocket-client==1.3.3; python_version >= "3.7"',
 'zipp (==3.8.1)']

setup_kwargs = {
    'name': 'c7n-kube',
    'version': '0.2.16',
    'description': 'Cloud Custodian - Kubernetes Provider',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
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
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
