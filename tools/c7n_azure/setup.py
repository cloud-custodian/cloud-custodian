# Automatically generated from poetry/pyproject.toml
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
['PyJWT>=1.7.1,<2.0.0',
 'adal>=1.2.2,<2.0.0',
 'applicationinsights>=0.11.9,<0.12.0',
 'apscheduler>=3.6.3,<4.0.0',
 'argcomplete (>=1.12.2,<2.0.0)',
 'attrs (>=20.3.0,<21.0.0)',
 'azure-cli-core>=2.0.81,<3.0.0',
 'azure-cosmos>=3.1.2,<4.0.0',
 'azure-cosmosdb-table>=1.0.6,<2.0.0',
 'azure-graphrbac>=0.61.1,<0.62.0',
 'azure-keyvault==1.1.0',
 'azure-mgmt-apimanagement>=0.1.0,<0.2.0',
 'azure-mgmt-applicationinsights>=0.2.0,<0.3.0',
 'azure-mgmt-authorization>=0.60.0,<0.61.0',
 'azure-mgmt-batch>=7.0.0,<8.0.0',
 'azure-mgmt-cdn>=4.0.0,<5.0.0',
 'azure-mgmt-cognitiveservices>=5.0.0,<6.0.0',
 'azure-mgmt-compute>=10.0.0,<11.0.0',
 'azure-mgmt-containerinstance>=1.5.0,<2.0.0',
 'azure-mgmt-containerregistry>=2.8.0,<3.0.0',
 'azure-mgmt-containerservice>=8.2.0,<9.0.0',
 'azure-mgmt-cosmosdb>=0.11.0,<0.12.0',
 'azure-mgmt-costmanagement>=0.1.0,<0.2.0',
 'azure-mgmt-databricks>=0.1.0,<0.2.0',
 'azure-mgmt-datafactory>=0.8.0,<0.9.0',
 'azure-mgmt-datalake-store>=0.5.0,<0.6.0',
 'azure-mgmt-dns>=3.0.0,<4.0.0',
 'azure-mgmt-eventgrid>=2.2.0,<3.0.0',
 'azure-mgmt-eventhub>=3.0.0,<4.0.0',
 'azure-mgmt-hdinsight>=1.4.0,<2.0.0',
 'azure-mgmt-iothub>=0.10.0,<0.11.0',
 'azure-mgmt-keyvault==1.1.0',
 'azure-mgmt-logic>=3.0.0,<4.0.0',
 'azure-mgmt-managementgroups>=0.2.0,<0.3.0',
 'azure-mgmt-monitor>=0.7.0,<0.8.0',
 'azure-mgmt-network>=9.0.0,<10.0.0',
 'azure-mgmt-policyinsights>=0.4.0,<0.5.0',
 'azure-mgmt-rdbms>=1.9.0,<2.0.0',
 'azure-mgmt-redis>=6.0.0,<7.0.0',
 'azure-mgmt-resource>=6,<7',
 'azure-mgmt-resourcegraph>=2.0.0,<3.0.0',
 'azure-mgmt-search>=2.1.0,<3.0.0',
 'azure-mgmt-sql>=0.16.0,<0.17.0',
 'azure-mgmt-storage>=7.1.0,<8.0.0',
 'azure-mgmt-subscription>=0.5.0,<0.6.0',
 'azure-mgmt-web>=0.44.0,<0.45.0',
 'azure-storage-blob>=2.1,<2.2',
 'azure-storage-file>=2.1.0,<3.0.0',
 'azure-storage-queue>=2.1,<2.2',
 'boto3 (>=1.17.10,<2.0.0)',
 'botocore (>=1.20.10,<2.0.0)',
 'c7n (>=0.9.11,<0.10.0)',
 'click>=7.0,<8.0',
 'distlib>=0.3.0,<0.4.0',
 'importlib-metadata (>=3.4.0,<4.0.0)',
 'jmespath (>=0.10.0,<0.11.0)',
 'jsonpickle (>=1.3,<2.0)',
 'jsonpickle==1.3',
 'jsonschema (>=3.2.0,<4.0.0)',
 'netaddr>=0.7.19,<0.8.0',
 'pyrsistent (>=0.17.3,<0.18.0)',
 'python-dateutil (>=2.8.1,<3.0.0)',
 'pyyaml (>=5.4.1,<6.0.0)',
 'requests>=2.22.0,<3.0.0',
 's3transfer (>=0.3.4,<0.4.0)',
 'six (>=1.15.0,<2.0.0)',
 'tabulate (>=0.8.8,<0.9.0)',
 'typing-extensions (>=3.7.4.3,<4.0.0.0)',
 'urllib3 (>=1.26.3,<2.0.0)',
 'zipp (>=3.4.0,<4.0.0)']

extras_require = \
{':python_version >= "3" and python_version < "4"': ['azure-functions>=1.0.8,<2.0.0']}

setup_kwargs = {
    'name': 'c7n-azure',
    'version': '0.7.10',
    'description': 'Cloud Custodian - Azure Support',
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
    'extras_require': extras_require,
    'python_requires': '>=3.6,<4.0',
}


setup(**setup_kwargs)
