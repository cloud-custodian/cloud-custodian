# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_gcp', 'c7n_gcp.actions', 'c7n_gcp.filters', 'c7n_gcp.resources']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (>=2.0.0,<3.0.0)',
 'attrs (>=22.2.0,<23.0.0)',
 'boto3 (>=1.26.50,<2.0.0)',
 'botocore (>=1.29.50,<2.0.0)',
 'c7n (>=0.9.22,<0.10.0)',
 'docutils (>=0.17.1,<0.18.0)',
 'google-api-core==2.10.2',
 'google-api-python-client>=2.0,<3.0',
 'google-auth>=2.1.0,<3.0.0',
 'google-cloud-logging>=3.2,<4.0',
 'google-cloud-monitoring>=2.5.0,<3.0.0',
 'google-cloud-storage>=1.42.2,<2.0.0',
 'grpcio==1.49.1',
 'importlib-metadata (>=4.13.0,<5.0.0)',
 'importlib-resources (>=5.10.2,<6.0.0)',
 'jmespath (>=1.0.1,<2.0.0)',
 'jsonschema (>=4.17.3,<5.0.0)',
 'pkgutil-resolve-name (>=1.3.10,<2.0.0)',
 'pyrate-limiter>=2.8.4,<3.0.0',
 'pyrsistent (>=0.19.3,<0.20.0)',
 'python-dateutil (>=2.8.2,<3.0.0)',
 'pyyaml (>=6.0,<7.0)',
 'requests==2.27.1',
 'retrying>=1.3.3,<2.0.0',
 's3transfer (>=0.6.0,<0.7.0)',
 'six (>=1.16.0,<2.0.0)',
 'tabulate (>=0.8.10,<0.9.0)',
 'typing-extensions (>=4.4.0,<5.0.0)',
 'urllib3 (>=1.26.14,<2.0.0)',
 'zipp (>=3.11.0,<4.0.0)']

setup_kwargs = {
    'name': 'c7n-gcp',
    'version': '0.4.21',
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
    'author_email': 'cloud-custodian@googlegroups.com',
    'project_urls': {
       'Homepage': 'https://cloudcustodian.io',
       'Documentation': 'https://cloudcustodian.io/docs/',
       'Source': 'https://github.com/cloud-custodian/cloud-custodian',
       'Issue Tracker': 'https://github.com/cloud-custodian/cloud-custodian/issues',
    },
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
