# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from io import open
from os import path
from setuptools import setup, find_packages
import sys

# read the contents of your README file
this_directory = path.abspath(path.dirname(__file__))
readme = path.join(this_directory, 'readme.md')
long_description = ''
if path.exists(readme):
    with open(readme, encoding='utf-8') as f:
        long_description = f.read()

# azure-functions are required if running in Azure Functions
# mode which is not supported for Python 2.7
extra_dependencies = ["azure-functions"] if sys.version_info[0] >= 3 else []

setup(
    name="c7n_azure",
    version='0.5.5',
    description="Cloud Custodian - Azure Support",
    long_description=long_description,
    long_description_content_type='text/markdown',
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        "custodian.resources": [
            'azure = c7n_azure.entry:initialize_azure']
    },
    install_requires=["azure-mgmt-authorization",
                      "azure-mgmt-apimanagement",
                      "azure-mgmt-applicationinsights",
                      "azure-mgmt-batch",
                      "azure-mgmt-cognitiveservices",
                      "azure-mgmt-cosmosdb",
                      "azure-mgmt-costmanagement",
                      "azure-mgmt-containerinstance",
                      "azure-mgmt-compute",
                      "azure-mgmt-cdn",
                      "azure-mgmt-containerregistry",
                      "azure-mgmt-containerservice",
                      "azure-mgmt-databricks",
                      "azure-mgmt-datalake-store",
                      "azure-mgmt-datafactory",
                      "azure-mgmt-dns",
                      "azure-mgmt-eventgrid",
                      "azure-mgmt-eventhub",
                      "azure-mgmt-iothub",
                      "azure-mgmt-keyvault",
                      "azure-mgmt-managementgroups",
                      "azure-mgmt-network>=4.0.0",
                      "azure-mgmt-redis",
                      "azure-mgmt-resource==2.1.0",
                      "azure-mgmt-sql",
                      "azure-mgmt-storage",
                      "azure-mgmt-web",
                      "azure-mgmt-monitor",
                      "azure-mgmt-policyinsights",
                      "azure-mgmt-logic",
                      "azure-cosmos",
                      "azure-graphrbac",
                      "azure-keyvault",
                      "azure-storage-blob",
                      # azure-cosmosdb-table has incompatible dependency ~=1.1
                      # Remove this when fixed:
                      # https://github.com/Azure/azure-cosmos-table-python/issues/39
                      "azure-storage-common~=2.0",
                      "azure-storage-queue",
                      "azure-storage-file",
                      "azure-cosmosdb-table",
                      "applicationinsights",
                      "apscheduler",
                      "distlib",
                      "jsonpickle",
                      "requests",
                      "PyJWT",
                      "c7n",
                      "azure-cli-core",
                      "adal",
                      "backports.functools_lru_cache",
                      "futures>=3.1.1",
                      "netaddr"] + extra_dependencies,
    package_data={str(''): [str('function_binding_resources/bin/*.dll'),
                            str('function_binding_resources/*.csproj'),
                            str('function_binding_resources/bin/*.json')]}
)
