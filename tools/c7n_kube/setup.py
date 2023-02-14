# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_kube',
 'c7n_kube.actions',
 'c7n_kube.resources',
 'c7n_kube.resources.apps',
 'c7n_kube.resources.core',
 'c7n_kube.resources.rbac']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (>=2.0.0,<3.0.0)',
 'attrs (>=22.2.0,<23.0.0)',
 'boto3 (>=1.26.51,<2.0.0)',
 'botocore (>=1.29.51,<2.0.0)',
 'c7n (>=0.9.22,<0.10.0)',
 'docutils (>=0.17.1,<0.18.0)',
 'importlib-metadata (>=4.13.0,<5.0.0)',
 'importlib-resources (>=5.10.2,<6.0.0)',
 'jmespath (>=1.0.1,<2.0.0)',
 'jsonschema (>=4.17.3,<5.0.0)',
 'kubernetes>=10.0.1,<11.0.0',
 'pkgutil-resolve-name (>=1.3.10,<2.0.0)',
 'pyrsistent (>=0.19.3,<0.20.0)',
 'python-dateutil (>=2.8.2,<3.0.0)',
 'pyyaml (>=6.0,<7.0)',
 's3transfer (>=0.6.0,<0.7.0)',
 'six (>=1.16.0,<2.0.0)',
 'tabulate (>=0.8.10,<0.9.0)',
 'typing-extensions (>=4.4.0,<5.0.0)',
 'urllib3 (>=1.26.14,<2.0.0)',
 'zipp (>=3.11.0,<4.0.0)']

entry_points = \
{'console_scripts': ['c7n-kates = c7n_kube.cli:cli']}

setup_kwargs = {
    'name': 'c7n-kube',
    'version': '0.2.21',
    'description': 'Cloud Custodian - Kubernetes Provider',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': "# Custodian Kubernetes Support\n\nCloud Custodian can run policies directly inside your cluster, reporting on \nresources that violate those policies, or blocking them altogether.\n\n# Running the server \n\nc7n-kates can be run and installed via poetry. `poetry install && poetry run c7n-kates`.  \n\n| name           | default   | description                                                  |\n|----------------|-----------|--------------------------------------------------------------|\n| --host         | 127.0.0.1 | (optional) The host that the server should listen on.        |\n| --port         | 8800      | (optional) The port the server will listen on.               |\n| --policy-dir   |           | Path to the policy directory.                                |\n| --on-exception | warn      | Action to take on an internal exception. One of: warn, deny. |\n| --cert         |           | Path to the certificate.                                     | \n| --ca-cert      |           | Path to the CA's certificate.                                |\n| --cert-key     |           | Path to the certificate's key.                               |\n\n# Generate a MutatingWebhookConfiguration\n\nAfter the server is running, you'll need to configure and install the \nMutatingWebhookConfiguration manually. To generate a webhook configuration, you\ncan run `poetry run c7n-kates --generate --endpoint $ENDPOINT_URL --policy-dir $DIR`, and \nit will generate an appropriate configuration for you, based on your policies.\n\nNote: some modification of the webhook configuration may be required. See the \n[documentation](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/) \non webhooks for more configuration.\n\n# Development\n\nYou can use [skaffold](https://github.com/GoogleContainerTools/skaffold/) to \nassist with testing and debugging this controller. Run `skaffold dev` in this\nfolder to deploy the local container into a local kubernetes cluster. It will \nautomatically redeploy it as files change.\n",
    'long_description_content_type': 'text/markdown',
    'author': 'Cloud Custodian Project',
    'author_email': 'cloud-custodian@googlegroups.com',
    'project_urls': {
       'Homepage': 'https://cloudcustodian.io',
       'Documentation': 'https://cloudcustodian.io/docs/',
       'Source': 'https://github.com/cloud-custodian/cloud-custodian',
       'Issue Tracker': 'https://github.com/cloud-custodian/cloud-custodian/issues',
    },
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'entry_points': entry_points,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
