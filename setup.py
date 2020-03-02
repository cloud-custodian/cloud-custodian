from pathlib import Path
from setuptools import setup, find_packages


setup(
    name="c7n",
    use_scm_version={'write_to': 'c7n/version.py', 'fallback_version': '0.9.0dev'},
    setup_requires=['setuptools_scm'],
    description="Cloud Custodian - Policy Rules Engine",
    long_description=Path('README.md').read_text(),
    long_description_content_type='text/markdown',
    classifiers=[
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    url="https://github.com/cloud-custodian/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    python_requires=">=3.6, <4",
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
        "certifi"]
)
