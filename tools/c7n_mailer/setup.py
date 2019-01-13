# Copyright 2015-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from io import open
from os import path
from setuptools import setup, find_packages

# *Any* updates here should also go into c7n_mailer/deploy.py for lambda packaging.
requires = [
    "Jinja2",
    "boto3",
    "jsonschema",
    "python-dateutil>=2.6",
    "ruamel.yaml==0.15.42",
    "datadog",
    "slackclient",
    "sendgrid",
    "ldap3",
    "redis"]

try:
    from concurrent import futures  # noqa F401
except ImportError:
    # The backport has SyntaxErrors under py36, so avoid installing it.
    # https://github.com/agronholm/pythonfutures/issues/41
    requires += ['futures']

# read the contents of your README file
this_directory = path.abspath(path.dirname(__file__))
readme = path.join(this_directory, 'README.md')
long_description = ''
if path.exists(readme):
    with open(readme, encoding='utf-8') as f:
        long_description = f.read()

setup(
    name="c7n_mailer",
    version='0.4.0',
    description="Cloud Custodian - Reference Mailer",
    long_description=long_description,
    long_description_content_type='text/markdown',
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/capitalone/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'c7n-mailer = c7n_mailer.cli:main',
            'c7n-mailer-replay = c7n_mailer.replay:main'
        ]
    },
    install_requires=requires,
    package_data={str(''): [str('msg-templates/*.j2')]},
)
