# Automatically generated from pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_gcp', 'c7n_gcp.actions', 'c7n_gcp.filters', 'c7n_gcp.resources']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (==2.0.0)',
 'attrs (==22.1.0)',
 'boto3 (==1.24.44)',
 'botocore (==1.27.44)',
 'c7n (==0.9.17)',
 'cachetools==5.2.0; python_version >= "3.7" and python_version < "4.0" and '
 '(python_version >= "3.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version >= "3.7")',
 'certifi==2022.6.15; python_version >= "3.7" and python_version < "4" and '
 '(python_version >= "2.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0") and (python_version >= "3.7" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version >= "3.7")',
 'charset-normalizer==2.1.0; python_version >= "3.7" and python_version < "4" '
 'and (python_version >= "2.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0") and (python_version >= "3.7" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version >= "3.7") and python_full_version >= "3.6.0"',
 'docutils (==0.17.1)',
 'google-api-core==2.8.2; python_version >= "3.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.6.0" and python_version >= "3.7"',
 'google-api-python-client==2.55.0; python_version >= "3.7"',
 'google-auth-httplib2==0.1.0; python_version >= "3.7"',
 'google-auth==2.9.1; (python_version >= "2.7" and python_full_version < '
 '"3.0.0") or (python_full_version >= "3.6.0")',
 'google-cloud-appengine-logging==1.1.3; python_version >= "3.7"',
 'google-cloud-audit-log==0.2.3; python_version >= "3.7"',
 'google-cloud-core==2.3.2; python_version >= "3.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.6.0" and python_version >= "3.7"',
 'google-cloud-logging==2.7.2; python_version >= "3.6"',
 'google-cloud-monitoring==2.10.1; python_version >= "3.7"',
 'google-cloud-storage==1.44.0; (python_version >= "2.7" and '
 'python_full_version < "3.0.0") or (python_full_version >= "3.6.0")',
 'google-crc32c==1.3.0; python_version >= "3.6" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.6.0" and python_version >= "3.6"',
 'google-resumable-media==2.3.3; python_version >= "3.6" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version >= "3.6"',
 'googleapis-common-protos==1.56.4; python_version >= "3.7" and '
 'python_full_version < "3.0.0" and (python_version >= "3.6" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version >= "3.6") or python_full_version >= "3.6.0" and '
 'python_version >= "3.7" and (python_version >= "3.6" and python_full_version '
 '< "3.0.0" or python_full_version >= "3.6.0" and python_version >= "3.6")',
 'grpc-google-iam-v1==0.12.4; python_version >= "3.6"',
 'grpcio-status==1.48.0; python_version >= "3.7" and (python_version >= "3.6" '
 'and python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version >= "3.6")',
 'grpcio==1.48.0; python_version >= "3.7" and (python_version >= "3.6" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version >= "3.6") and (python_version >= "3.7" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version >= "3.7")',
 'httplib2==0.20.4; python_version >= "3.7" and python_full_version < "3.0.0" '
 'or python_full_version >= "3.4.0" and python_version >= "3.7"',
 'idna==3.3; python_version >= "3.7" and python_version < "4" and '
 '(python_version >= "2.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0") and (python_version >= "3.7" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version >= "3.7")',
 'importlib-metadata (==4.12.0)',
 'importlib-resources (==5.9.0)',
 'jmespath (==1.0.1)',
 'jsonschema (==4.9.0)',
 'pkgutil-resolve-name (==1.3.10)',
 'proto-plus==1.20.6; python_version >= "3.7"',
 'protobuf==3.20.1; python_version >= "3.7" and python_full_version < "3.0.0" '
 'and (python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version >= "3.6") or '
 'python_full_version >= "3.6.0" and python_version >= "3.7" and '
 '(python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version >= "3.6")',
 'pyasn1-modules==0.2.8; python_version >= "3.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.6.0" and python_version >= "3.7"',
 'pyasn1==0.4.8; python_version >= "3.7" and python_full_version < "3.0.0" and '
 'python_version < "4" and (python_version >= "3.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.6.0" and python_version >= "3.7") or '
 'python_full_version >= "3.6.0" and python_version >= "3.7" and '
 'python_version < "4" and (python_version >= "3.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.6.0" and python_version >= "3.7")',
 'pyparsing==3.0.9; python_full_version >= "3.6.8" and python_version >= "3.7"',
 'pyrsistent (==0.18.1)',
 'python-dateutil (==2.8.2)',
 'pyyaml (==6.0)',
 'ratelimiter==1.2.0.post0',
 'requests==2.28.1; python_version >= "3.7" and python_version < "4" and '
 '(python_version >= "2.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0") and (python_version >= "3.7" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version >= "3.7")',
 'retrying==1.3.3',
 'rsa==4.9; python_version >= "3.6" and python_version < "4" and '
 '(python_version >= "3.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version >= "3.7")',
 's3transfer (==0.6.0)',
 'six (==1.16.0)',
 'six==1.16.0; python_version >= "3.7" and python_full_version < "3.0.0" and '
 '(python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version >= "3.6") and '
 '(python_version >= "3.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version >= "3.7") or '
 'python_full_version >= "3.6.0" and python_version >= "3.7" and '
 '(python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version >= "3.6") and '
 '(python_version >= "3.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version >= "3.7")',
 'tabulate (==0.8.10)',
 'typing-extensions (==4.3.0)',
 'uritemplate==4.1.1; python_version >= "3.7"',
 'urllib3 (==1.26.11)',
 'urllib3==1.26.11; python_version >= "3.7" and python_full_version < "3.0.0" '
 'and python_version < "4" and (python_version >= "2.7" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0") and '
 '(python_version >= "3.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version >= "3.7") or '
 'python_full_version >= "3.6.0" and python_version < "4" and python_version '
 '>= "3.7" and (python_version >= "2.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0") and (python_version >= "3.7" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version >= "3.7")',
 'zipp (==3.8.1)']

setup_kwargs = {
    'name': 'c7n-gcp',
    'version': '0.4.16',
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
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
