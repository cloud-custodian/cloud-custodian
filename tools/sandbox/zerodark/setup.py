# Copyright 2017-2018 Capital One Services, LLC
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
from io import open
from setuptools import setup, find_packages


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()


setup(
    name="zerodark",
    version='0.0.1',
    description="Monitoring and analysis",
    long_description=read('readme.md'),
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    author="Kapil Thangavelu",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'zero-metrics = zerodark.metrics:cli',
            'zero-ipdb = zerodark.ipdb:cli',
            'zero-flow = zerodark.floweni:cli']},
    install_requires=[
        "boto3>=1.4.7",
        "botocore>=1.7.37",
        "pyyaml",
        "sqlalchemy",
        "humanize",
        "c7n_org",
        "c7n",
        "jsonschema",
        "click",
        "tabulate",
        "influxdb",
        "ipaddress"
    ],
)
