from setuptools import setup, find_packages


setup(
    name="c7n",
    version='0.8.9.2',
    description="Cloud Custodian - Policy Rules Engine",
    long_description_markdown_filename='README.md',
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
    install_requires=["boto3", "pyyaml", "jsonschema"],
)

