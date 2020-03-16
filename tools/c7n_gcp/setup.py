# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_gcp', 'c7n_gcp.actions', 'c7n_gcp.filters', 'c7n_gcp.resources']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (>=1.11.1,<2.0.0)',
 'attrs (>=19.3.0,<20.0.0)',
 'boto3 (>=1.12.21,<2.0.0)',
 'botocore (>=1.15.21,<2.0.0)',
 'c7n (>=0.9.0,<0.10.0)',
 'docutils (>=0.15.2,<0.16.0)',
 'google-api-python-client>=1.7,<2.0',
 'google-auth>=1.11.0,<2.0.0',
 'google-cloud-logging>=1.14,<2.0',
 'google-cloud-monitoring>=0.34.0,<0.35.0',
 'importlib-metadata (>=1.5.0,<2.0.0)',
 'jmespath (>=0.9.5,<0.10.0)',
 'jsonschema (>=3.2.0,<4.0.0)',
 'pyrsistent (>=0.15.7,<0.16.0)',
 'python-dateutil (>=2.8.1,<3.0.0)',
 'pyyaml (>=5.3,<6.0)',
 'ratelimiter>=1.2.0,<2.0.0',
 'retrying>=1.3.3,<2.0.0',
 's3transfer (>=0.3.3,<0.4.0)',
 'six (>=1.14.0,<2.0.0)',
 'tabulate (>=0.8.6,<0.9.0)',
 'urllib3 (>=1.25.8,<2.0.0)',
 'zipp (>=3.1.0,<4.0.0)']

setup_kwargs = {
    'name': 'c7n-gcp',
    'version': '0.3.8',
    'description': 'Cloud Custodian - Google Cloud Provider',
    'long_description': '# Custodian GCP Support\n\nStatus - Alpha\n\n# Features\n\n - Serverless ✅\n - Api Subscriber ✅\n - Metrics ✅\n - Resource Query ✅\n - Multi Account (c7n-org) ✅\n\n# Getting Started\n\n\n## via pip\n\n```\npip install c7n_gcp\n```\n\nBy default custodian will use credentials associated to the gcloud cli, which will generate\nwarnings per google.auth (https://github.com/googleapis/google-auth-library-python/issues/292)\n\nThe recommended authentication form for production usage is to create a service account and\ncredentials, which will be picked up via by the custodian cli via setting the\n*GOOGLE_APPLICATION_CREDENTIALS* environment variable.\n\n\n# Serverless\n\nCustodian supports both periodic and api call events for serverless policy execution.\n',
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
