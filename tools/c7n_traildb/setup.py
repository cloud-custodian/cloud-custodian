# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from setuptools import setup

setup(
    name="c7n_traildb",
    version='0.1',
    description="Cloud Custodian - Cloud Trail Tools",
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    license="Apache-2.0",
    py_modules=['c7n_traildb'],
    entry_points={
        'console_scripts': [
            'c7n-traildb = c7n_traildb.traildb:main',
            'c7n-trailts = c7n_traildb.trailts:trailts',
            'c7n-trailes = c7n_traildb.trailes:trailes',
        ]},
    install_requires=["c7n", "click", "jsonschema", "influxdb"],
)
