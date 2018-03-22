

from setuptools import setup, find_packages

setup(
    name="c7n_azure",
    version='0.1',
    description="Cloud Custodian - Azure Support",
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/capitalone/cloud-custodian",
    maintainer="Kapil Thangavelu",
    maintainer_email="kapil.foss@gmail.com",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        "custodian.resources": [
            'azure = c7n_azure.entry:initialize_azure']
            },
    install_requires=["c7n", "click", "azure", "azure-cli-core"]
)
