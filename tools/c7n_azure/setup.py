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

# read the contents of your README file
this_directory = path.abspath(path.dirname(__file__))
readme = path.join(this_directory, 'readme.md')
long_description = ''
if path.exists(readme):
    with open(readme, encoding='utf-8') as f:
        long_description = f.read()

setup(
    name="c7n_azure",
    version='0.1',
    description="Cloud Custodian - Azure Support",
    long_description=long_description,
    long_description_content_type='text/markdown',
    include_package_data=True,
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/capitalone/cloud-custodian",
    maintainer="Kapil Thangavelu",
    maintainer_email="kapil.foss@gmail.com",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        "custodian.resources": [
            'azure = c7n_azure.entry:initialize_azure']
    },
    install_requires=["azure-mgmt",
                      "azure-graphrbac",
                      "azure-storage-blob",
                      "azure-storage-queue",
                      "requests",
                      "PyJWT",
                      "c7n",
                      "requests",
                      "azure-cli-core<=2.0.40",
                      "adal~=0.5.0",
                      "backports.functools_lru_cache",
                      "futures>=3.1.1"],

)
