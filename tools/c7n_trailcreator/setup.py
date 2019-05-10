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

from setuptools import setup

setup(
    name="c7n_trailcreator",
    version='0.1',
    description="Cloud Custodian - Retroactive Tag Creators from CloudTrail",
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/capitalone/cloud-custodian",
    license="Apache-2.0",
    py_modules=['c7n_trailcreator'],
    entry_points={
        'console_scripts': [
            'c7n-trailcreator = c7n_trailcreator.trailcreator:cli',
        ]},
    install_requires=["c7n", "click"],
)
