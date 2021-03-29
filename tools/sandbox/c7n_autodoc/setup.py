# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from setuptools import setup
import os

description = ""
if os.path.exists('README.md'):
    description = open('README.md', 'r').read()

setup(
    name="c7n_autodoc",
    version='0.3',
    description="Cloud Custodian - Automated Policy Documentation",
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    long_description=description,
    long_description_content_type='text/markdown',
    author="Ryan Ash",
    author_email="ryanash@gmail.com",
    license="Apache-2.0",
    py_modules=["c7n_autodoc"],
    install_requires=["c7n", "pyyaml>=4.2b4", "boto3", "jinja2>=2.11.3", "jsonschema"]
)
