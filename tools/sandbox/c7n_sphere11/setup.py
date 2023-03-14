# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from setuptools import setup, find_packages

setup(
    name="c7n_sphere11",
    version='0.1.1',
    description="Cloud Custodian - Sphere11 - Resource Locking",
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'sphere-admin = c7n_sphere11.admin:admin',
            'c7n-sphere11 = c7n_sphere11.cli:cli']},
    install_requires=["click", "tabulate"],
)
