# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from setuptools import setup, find_packages
import os

description = ""
if os.path.exists('README.md'):
    description = open('README.md').read()

setup(
    name="c7n_salactus",
    version='0.3.0',
    description="Cloud Custodian - Salactus S3",
    long_description=description,
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
            'c7n-salactus = c7n_salactus.cli:cli']},
    install_requires=["c7n", "click", "rq", "redis"],
)
