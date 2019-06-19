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

from setuptools import setup, find_packages

setup(
    name="c7n_gcp",
    version='0.3.1',
    description="Cloud Custodian - Multi Account",
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        "custodian.resources": [
            'gcp = c7n_gcp.entry:initialize_gcp']
    },
    install_requires=[
        "c7n", "click",
        "ratelimiter", "retrying",
        "google-api-python-client>=1.7.3",
        "google-auth-httplib2>=0.0.3",
        "google-auth>=1.4.1",
        "google-cloud-logging>=1.6.0",
        "google-cloud-monitoring>=0.3.0"
    ]
)
