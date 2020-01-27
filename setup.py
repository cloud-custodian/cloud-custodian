import os
from io import open
from setuptools import setup, find_packages


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()


setup(
    name="c7n",
    version='0.8.46.0',
    description="Cloud Custodian - Policy Rules Engine",
    long_description=read('README.md'),
    long_description_content_type='text/markdown',
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing",
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3, !=3.4, !=3.5, <4'",
    entry_points={
        'console_scripts': [
            'custodian = c7n.cli:main']},
    install_requires=[
        "boto3>=1.9.228",
        "botocore>=1.13.46",
        "python-dateutil>=2.6,<3.0.0",
        "PyYAML>=5.1",
        "jsonschema",
        "jsonpatch>=1.21",
        "argcomplete",
        "tabulate>=0.8.2",
        "urllib3",
        "certifi"
    ],
    extra_requires={
        ":python_version<'3.3'": ["backports.functools-lru-cache"]
    }
)
