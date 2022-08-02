# Automatically generated from pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_azure',
 'c7n_azure.actions',
 'c7n_azure.container_host',
 'c7n_azure.provisioning',
 'c7n_azure.resources']

package_data = \
{'': ['*']}

install_requires = \
['adal==1.2.7',
 'applicationinsights==0.11.10',
 'apscheduler==3.9.1; (python_version >= "2.7" and python_full_version < '
 '"3.0.0") or (python_full_version >= "3.5.0" and python_version < "4")',
 'argcomplete (==2.0.0)',
 'attrs (==22.1.0)',
 'azure-common==1.1.28; python_version >= "3.6"',
 'azure-core==1.24.2; python_version >= "3.6"',
 'azure-cosmos==3.2.0',
 'azure-cosmosdb-nspkg==2.0.2',
 'azure-cosmosdb-table==1.0.6',
 'azure-functions==1.11.2; python_version >= "3" and python_version < "4"',
 'azure-graphrbac==0.61.1',
 'azure-identity==1.10.0; python_version >= "3.6"',
 'azure-keyvault-certificates==4.4.0; python_version >= "3.6"',
 'azure-keyvault-keys==4.5.1; python_version >= "3.6"',
 'azure-keyvault-secrets==4.4.0; python_version >= "3.6"',
 'azure-keyvault==4.2.0',
 'azure-mgmt-advisor==9.0.0',
 'azure-mgmt-apimanagement==1.0.0',
 'azure-mgmt-applicationinsights==1.0.0',
 'azure-mgmt-authorization==1.0.0',
 'azure-mgmt-batch==15.0.0',
 'azure-mgmt-cdn==10.0.0',
 'azure-mgmt-cognitiveservices==11.0.0',
 'azure-mgmt-compute==19.0.0',
 'azure-mgmt-containerinstance==7.0.0',
 'azure-mgmt-containerregistry==8.0.0b1',
 'azure-mgmt-containerservice==15.1.0',
 'azure-mgmt-core==1.3.1; python_version >= "3.6"',
 'azure-mgmt-cosmosdb==6.4.0',
 'azure-mgmt-costmanagement==1.0.0',
 'azure-mgmt-databricks==1.0.0b1',
 'azure-mgmt-datafactory==1.1.0',
 'azure-mgmt-datalake-store==1.0.0',
 'azure-mgmt-dns==8.0.0b1',
 'azure-mgmt-eventgrid==8.0.0',
 'azure-mgmt-eventhub==8.0.0',
 'azure-mgmt-frontdoor==1.0.1; python_version >= "3.6"',
 'azure-mgmt-hdinsight==7.0.0',
 'azure-mgmt-iothub==1.0.0',
 'azure-mgmt-keyvault==8.0.0',
 'azure-mgmt-logic==9.0.0',
 'azure-mgmt-managementgroups==1.0.0b1',
 'azure-mgmt-monitor==2.0.0',
 'azure-mgmt-msi==1.0.0',
 'azure-mgmt-network==17.1.0',
 'azure-mgmt-policyinsights==1.0.0',
 'azure-mgmt-rdbms==8.1.0',
 'azure-mgmt-redis==12.0.0',
 'azure-mgmt-resource==16.1.0',
 'azure-mgmt-resourcegraph==7.0.0',
 'azure-mgmt-search==8.0.0',
 'azure-mgmt-security==1.0.0',
 'azure-mgmt-servicefabric==1.0.0',
 'azure-mgmt-sql==1.0.0',
 'azure-mgmt-storage==17.1.0',
 'azure-mgmt-subscription==1.0.0',
 'azure-mgmt-trafficmanager==0.51.0',
 'azure-mgmt-web==2.0.0',
 'azure-nspkg==3.0.2',
 'azure-storage-blob==12.13.0; python_version >= "3.6"',
 'azure-storage-common==2.1.0',
 'azure-storage-file-share==12.9.0; python_version >= "3.6"',
 'azure-storage-file==2.1.0',
 'azure-storage-queue==12.4.0; python_version >= "3.6"',
 'backports.zoneinfo==0.2.1; python_version >= "3.6" and python_full_version < '
 '"3.0.0" and python_version < "3.9" and (python_version >= "3.6" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version < "4" and python_version >= "3.6") or python_full_version >= '
 '"3.5.0" and python_version < "3.9" and python_version >= "3.6" and '
 '(python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.6.0" and python_version < "4" and python_version '
 '>= "3.6")',
 'boto3 (==1.24.44)',
 'botocore (==1.27.44)',
 'c7n (==0.9.17)',
 'certifi==2022.6.15; python_version >= "3.7" and python_version < "4"',
 'cffi==1.15.1; python_version >= "3.6"',
 'charset-normalizer==2.1.0; python_version >= "3.7" and python_version < "4" '
 'and python_full_version >= "3.6.0"',
 'click==8.1.3; python_version >= "3.7"',
 'colorama==0.4.5; python_version >= "3.7" and python_full_version < "3.0.0" '
 'and platform_system == "Windows" or platform_system == "Windows" and '
 'python_version >= "3.7" and python_full_version >= "3.5.0"',
 'cryptography==37.0.4; python_version >= "3.6"',
 'distlib==0.3.5',
 'docutils (==0.17.1)',
 'idna==3.3; python_version >= "3.7" and python_version < "4"',
 'importlib-metadata (==4.12.0)',
 'importlib-metadata==4.12.0; python_version < "3.8" and python_version >= '
 '"3.7"',
 'importlib-resources (==5.9.0)',
 'isodate==0.6.1; python_version >= "3.6"',
 'jmespath (==1.0.1)',
 'jmespath==1.0.1; python_version >= "3.7"',
 'jsonschema (==4.9.0)',
 'msal-extensions==1.0.0; python_version >= "3.6"',
 'msal==1.18.0; python_version >= "3.6"',
 'msrest==0.7.1; python_version >= "3.6"',
 'msrestazure==0.6.4',
 'netaddr==0.7.20',
 'oauthlib==3.2.0; python_version >= "3.6" and python_full_version < "3.0.0" '
 'or python_full_version >= "3.4.0" and python_version >= "3.6"',
 'pkgutil-resolve-name (==1.3.10)',
 'portalocker==2.5.1',
 'pycparser==2.21; python_version >= "3.6" and python_full_version < "3.0.0" '
 'or python_version >= "3.6" and python_full_version >= "3.4.0"',
 'pyjwt==2.4.0; python_version >= "3.6"',
 'pyrsistent (==0.18.1)',
 'python-dateutil (==2.8.2)',
 'python-dateutil==2.8.2; python_version >= "2.7" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.3.0"',
 'pytz-deprecation-shim==0.1.0.post0; python_version >= "3.6" and '
 'python_full_version < "3.0.0" or python_full_version >= "3.6.0" and '
 'python_version < "4" and python_version >= "3.6"',
 'pytz==2022.1; python_version >= "2.7" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.5.0" and python_version < "4"',
 'pyyaml (==6.0)',
 'requests-oauthlib==1.3.1; python_version >= "3.6" and python_full_version < '
 '"3.0.0" or python_full_version >= "3.4.0" and python_version >= "3.6"',
 'requests==2.28.1; python_version >= "3.7" and python_version < "4"',
 's3transfer (==0.6.0)',
 'six (==1.16.0)',
 'six==1.16.0; python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.5.0" and python_version < "4" and python_version '
 '>= "3.6"',
 'tabulate (==0.8.10)',
 'typing-extensions (==4.3.0)',
 'typing-extensions==4.3.0; python_version < "3.8" and python_version >= "3.7"',
 'tzdata==2022.1; python_version >= "3.6" and python_full_version < "3.0.0" '
 'and platform_system == "Windows" or python_full_version >= "3.6.0" and '
 'python_version < "4" and python_version >= "3.6" and platform_system == '
 '"Windows"',
 'tzlocal==4.2; python_version >= "3.6" and python_full_version < "3.0.0" or '
 'python_full_version >= "3.5.0" and python_version < "4" and python_version '
 '>= "3.6"',
 'urllib3 (==1.26.11)',
 'urllib3==1.26.11; python_version >= "3.7" and python_full_version < "3.0.0" '
 'and python_version < "4" or python_full_version >= "3.6.0" and '
 'python_version < "4" and python_version >= "3.7"',
 'zipp (==3.8.1)',
 'zipp==3.8.1; python_version < "3.8" and python_version >= "3.7"']

setup_kwargs = {
    'name': 'c7n-azure',
    'version': '0.7.16',
    'description': 'Cloud Custodian - Azure Support',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': '\n# Cloud Custodian - Azure Support\n\nThis a plugin to Cloud Custodian that adds Azure support.\n\n## Install Cloud Custodian and Azure Plugin\n\nThe Azure provider must be installed as a separate package in addition to c7n. \n\n    $ git clone https://github.com/cloud-custodian/cloud-custodian.git\n    $ virtualenv custodian\n    $ source custodian/bin/activate\n    (custodian) $ pip install -e cloud-custodian/.\n    (custodian) $ pip install -e cloud-custodian/tools/c7n_azure/.\n\n\n## Write your first policy\n\nA policy specifies the following items:\n\n- The type of resource to run the policy against\n- Filters to narrow down the set of resources\n- Actions to take on the filtered set of resources\n\nFor this tutorial we will add a tag to all virtual machines with the name "Hello" and the value "World".\n\nCreate a file named ``custodian.yml`` with this content:\n\n    policies:\n        - name: my-first-policy\n          description: |\n            Adds a tag to all virtual machines\n          resource: azure.vm\n          actions:\n            - type: tag\n              tag: Hello\n              value: World\n\n## Run your policy\n\nFirst, choose one of the supported authentication mechanisms and either log in to Azure CLI or set\nenvironment variables as documented in [Authentication](https://cloudcustodian.io/docs/azure/authentication.html#azure-authentication).\n\n    custodian run --output-dir=. custodian.yml\n\n\nIf successful, you should see output similar to the following on the command line\n\n    2016-12-20 08:35:06,133: custodian.policy:INFO Running policy my-first-policy resource: azure.vm\n    2016-12-20 08:35:07,514: custodian.policy:INFO policy: my-first-policy resource:azure.vm has count:1 time:1.38\n    2016-12-20 08:35:08,188: custodian.policy:INFO policy: my-first-policy action: tag: 1 execution_time: 0.67\n\n\nYou should also find a new ``my-first-policy`` directory with a log and other\nfiles (subsequent runs will append to the log by default rather than\noverwriting it). \n\n## Links\n- [Getting Started](https://cloudcustodian.io/docs/azure/gettingstarted.html)\n- [Example Scenarios](https://cloudcustodian.io/docs/azure/examples/index.html)\n- [Example Policies](https://cloudcustodian.io/docs/azure/policy/index.html)\n\n\n\n\n',
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
