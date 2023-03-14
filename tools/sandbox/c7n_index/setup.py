# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from setuptools import setup, find_packages

setup(
    name="c7n_indexer",
    version='0.0.2',
    description="Cloud Custodian - Metrics/Resource Indexer",
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'c7n-indexer = c7n_index.metrics:cli']},
    install_requires=["c7n", "click", "influxdb", "elasticsearch"],
)
