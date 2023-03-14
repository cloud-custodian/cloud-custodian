# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from setuptools import setup

setup(
    name="c7n_sentry",
    version='0.1',
    description="Cloud Custodian - Sentry",
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    license="Apache-2.0",
    py_modules=['c7nsentry'],
    entry_points={
        'console_scripts': [
            'c7n-sentry = c7n_sentry.c7nsentry:main']},
    install_requires=["c7n"],
)
