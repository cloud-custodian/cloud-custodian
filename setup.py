import os
from io import open
from setuptools import setup, find_packages


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()


setup(
    name="c7n",
    version='0.8.43.0',
    description="Cloud Custodian - Policy Rules Engine",
    long_description=read('README.rst'),
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/capitalone/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'custodian = c7n.cli:main']},
    install_requires=[
        "boto3>=1.9.94",
        "botocore>=1.12.94",
        "python-dateutil>=2.6,<3.0.0",
        "PyYAML>=4.2b4",
        "jsonschema",
        "jsonpatch>=1.21",
        "argcomplete",
# Pinned due to azure-core-cli pin on tabulate
# https://github.com/Azure/azure-cli/issues/8567
        "tabulate==0.8.2"
    ],
)
