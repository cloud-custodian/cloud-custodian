# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_gcp', 'c7n_gcp.actions', 'c7n_gcp.filters', 'c7n_gcp.resources']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (>=1.12.3,<2.0.0)',
 'attrs (>=21.2.0,<22.0.0)',
 'boto3 (>=1.18.46,<2.0.0)',
 'botocore (>=1.21.46,<2.0.0)',
 'c7n (>=0.9.14,<0.10.0)',
 'google-api-python-client>=2.0,<3.0',
 'google-auth>=2.1.0,<3.0.0',
 'google-cloud-logging>=2.6,<3.0',
 'google-cloud-monitoring>=2.5.0,<3.0.0',
 'google-cloud-storage>=1.42.2,<2.0.0',
 'importlib-metadata (>=4.8.1,<5.0.0)',
 'jmespath (>=0.10.0,<0.11.0)',
 'jsonschema (>=3.2.0,<4.0.0)',
 'pyrsistent (>=0.18.0,<0.19.0)',
 'python-dateutil (>=2.8.2,<3.0.0)',
 'pytz>=2021.1,<2022.0',
 'pyyaml (>=5.4.1,<6.0.0)',
 'ratelimiter>=1.2.0,<2.0.0',
 'retrying>=1.3.3,<2.0.0',
 's3transfer (>=0.5.0,<0.6.0)',
 'six (>=1.16.0,<2.0.0)',
 'tabulate (>=0.8.9,<0.9.0)',
 'typing-extensions (>=3.10.0.2,<4.0.0.0)',
 'urllib3 (>=1.26.7,<2.0.0)',
 'zipp (>=3.5.0,<4.0.0)']

setup_kwargs = {
    'name': 'c7n-gcp',
    'version': '0.4.13',
    'description': 'Cloud Custodian - Google Cloud Provider',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': '# Custodian GCP Support\n\nStatus - Alpha\n\n# Features\n\n - Serverless ✅\n - Api Subscriber ✅\n - Metrics ✅\n - Resource Query ✅\n - Multi Account (c7n-org) ✅\n\n# Getting Started\n\n\n## via pip\n\n```\npip install c7n_gcp\n```\n\nBy default custodian will use credentials associated to the gcloud cli, which will generate\nwarnings per google.auth (https://github.com/googleapis/google-auth-library-python/issues/292)\n\nThe recommended authentication form for production usage is to create a service account and\ncredentials, which will be picked up via by the custodian cli via setting the\n*GOOGLE_APPLICATION_CREDENTIALS* environment variable.\n\n\n# Serverless\n\nCustodian supports both periodic and api call events for serverless\npolicy execution.\n\nGCP Cloud Functions require cloudbuild api be enabled on the project\nthe functions are deployed to.\n\nPeriodic execution mode also requires cloudscheduler api be enabled on\na project. Cloudscheduler usage also requires an app engine instance\nin the same region as the function deployment.\n',
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
