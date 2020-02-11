import os
import sys
from io import open
from setuptools import setup, find_packages


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()


REQUIREMENTS = [
    "boto3>=1.9.228",
    "botocore>=1.13.46",
    "python-dateutil>=2.6,<3.0.0",
    "PyYAML>=5.1",
    "jsonschema",
    "jsonpatch>=1.21",
    "argcomplete",
    "tabulate>=0.8.2",
    "urllib3",
    "certifi",
] if sys.version_info > (3,) else [
    "argcomplete==1.11.1",
    "attrs==19.3.0",
    "backports.functools-lru-cache==1.6.1",
    "boto3==1.11.15",
    "botocore==1.14.15",
    "certifi==2019.11.28",
    "configparser==4.0.2",
    "contextlib2==0.6.0.post1",
    "docutils==0.15.2",
    "functools32==3.2.3.post2",
    "futures==3.3.0",
    "importlib-metadata==1.5.0",
    "jmespath==0.9.4",
    "jsonpatch==1.25",
    "jsonpointer==2.0",
    "jsonschema==3.2.0",
    "pathlib2==2.3.5",
    "pyrsistent==0.15.7",
    "python-dateutil==2.8.1",
    "PyYAML==5.3",
    "s3transfer==0.3.3",
    "scandir==1.10.0",
    "six==1.14.0",
    "tabulate==0.8.6",
    "urllib3==1.25.8",
    "zipp==1.1.0",
]


setup(
    name="c7n",
    use_scm_version={'write_to': 'c7n/version.py', 'fallback_version': '0.9.0dev'},
    setup_requires=['setuptools_scm'],
    description="Cloud Custodian - Policy Rules Engine",
    long_description=read('README.md'),
    long_description_content_type='text/markdown',
    classifiers=[
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing',
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
    install_requires=REQUIREMENTS,
)
