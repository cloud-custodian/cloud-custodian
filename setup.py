import os
from setuptools import setup, find_packages


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name="c7n",
    version='0.8.21.0',
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
    install_requires=["boto3", "pyyaml==3.11", "jsonschema", "skew", "ipaddress"],
)

