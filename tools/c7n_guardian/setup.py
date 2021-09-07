# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from setuptools import setup, find_packages
import os

description = ""
if os.path.exists('readme.md'):
    description = open('readme.md').read()


setup(
    name="c7n_guardian",
    version='0.3.3',
    description="Cloud Custodian - Multi Account Guard Duty Setup",
    long_description=description,
    long_description_content_type='text/markdown',
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    author="Kapil Thangavelu",
    author_email="kapil.foss@gmail.com",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'c7n-guardian = c7n_guardian.cli:cli']},
    install_requires=["c7n", "click", "jsonschema", "pyyaml>=4.2b4"]
)
