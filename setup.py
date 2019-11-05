import os
from io import open
from setuptools import setup, find_packages


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()


setup(
    name="c7n",
    version='0.8.45.1',
    description="Cloud Custodian - Policy Rules Engine",
    long_description=read('README.md'),
    long_description_content_type='text/markdown',
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'custodian = c7n.cli:main']},
    install_requires=[
        "boto3>=1.9.228",
        "botocore>=1.12.228",
        "python-dateutil>=2.6,<2.8.1",
        "PyYAML>=4.2b4",
        "jsonschema",
        "jsonpatch>=1.21",
        "argcomplete",
        "tabulate>=0.8.2",
        "urllib3",
        "certifi"
    ],
)
