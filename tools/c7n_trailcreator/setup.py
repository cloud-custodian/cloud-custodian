# Copyright 2019 Amazon.com, Inc. or its affiliates.
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

import os
from setuptools import setup, find_packages

long_description = ""
if os.path.exists('readme.md'):
    long_description = open("readme.md", "r").read()

setup(
    name="c7n_trailcreator",
    version='0.1.5',
    description="Cloud Custodian - Retroactive Tag Resource Creators from CloudTrail",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/capitalone/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'c7n-trailcreator = c7n_trailcreator.trailcreator:cli',
        ]},
    install_requires=["c7n", "click", "c7n-org>=0.5.2"],
)
