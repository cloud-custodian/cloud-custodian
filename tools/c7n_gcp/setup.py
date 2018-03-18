# Copyright 2016 Capital One Services, LLC
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
    version='0.1',
    description="Cloud Custodian - Multi Account",
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/capitalone/cloud-custodian",
    author="Kapil Thangavelu",
    author_email="kapil.foss@gmail.com",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        "custodian.resources": [
            'gcp = c7n_gcp.entry:initialize_gcp']
            },
    install_requires=["c7n", "click", "google-api-python-client", "ratelimiter", "retrying"]
)
