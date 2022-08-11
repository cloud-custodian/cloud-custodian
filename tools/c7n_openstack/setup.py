# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_openstack', 'c7n_openstack.resources']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (>=2.0.0,<3.0.0)',
 'attrs (>=22.1.0,<23.0.0)',
 'boto3 (>=1.24.44,<2.0.0)',
 'botocore (>=1.27.44,<2.0.0)',
 'c7n (>=0.9.18,<0.10.0)',
 'docutils (>=0.17.1,<0.18.0)',
 'importlib-metadata (>=4.12.0,<5.0.0)',
 'importlib-resources (>=5.9.0,<6.0.0)',
 'jmespath (>=1.0.1,<2.0.0)',
 'jsonschema (>=4.9.0,<5.0.0)',
 'openstacksdk>=0.52.0,<0.53.0',
 'pkgutil-resolve-name (>=1.3.10,<2.0.0)',
 'pyrsistent (>=0.18.1,<0.19.0)',
 'python-dateutil (>=2.8.2,<3.0.0)',
 'pyyaml (>=6.0,<7.0)',
 's3transfer (>=0.6.0,<0.7.0)',
 'six (>=1.16.0,<2.0.0)',
 'tabulate (>=0.8.10,<0.9.0)',
 'typing-extensions (>=4.3.0,<5.0.0)',
 'urllib3 (>=1.26.11,<2.0.0)',
 'zipp (>=3.8.1,<4.0.0)']

setup_kwargs = {
    'name': 'c7n-openstack',
    'version': '0.1.8',
    'description': 'Cloud Custodian - OpenStack Provider',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': "# Custodian OpenStack Support\n\nWork in Progress - Not Ready For Use.\n\n## Quick Start\n\n### Installation\n\n```\npip install c7n_openstack\n```\n\n### OpenStack Environment Configration\n\nC7N will find cloud config for as few as 1 cloud and as many as you want to put in a config file.\nIt will read environment variables and config files, and it also contains some vendor specific default\nvalues so that you don't have to know extra info to use OpenStack:\n\n* If you have a config file, you will get the clouds listed in it\n* If you have environment variables, you will get a cloud named envvars\n* If you have neither, you will get a cloud named defaults with base defaults\n\nCreate a clouds.yml file:\n\n```yaml\nclouds:\n demo:\n   region_name: RegionOne\n   auth:\n     username: 'admin'\n     password: XXXXXXX\n     project_name: 'admin'\n     domain_name: 'Default'\n     auth_url: 'https://montytaylor-sjc.openstack.blueboxgrid.com:5001/v2.0'\n```\n\nPlease note: c7n will look for a file called `clouds.yaml` in the following locations:\n\n* Current Directory\n* ~/.config/openstack\n* /etc/openstack\n\nMore information at [https://pypi.org/project/os-client-config](https://pypi.org/project/os-client-config)\n\n### Create a c7n policy yaml file as follows:\n\n```yaml\npolicies:\n- name: demo\n  resource: openstack.flavor\n  filters:\n  - type: value\n    key: vcpus\n    value: 1\n    op: gt\n```\n\n### Run c7n and report the matched resources:\n\n```sh\nmkdir -p output\ncustodian run demo.yaml -s output\ncustodian report demo.yaml -s output --format grid\n```\n\n## Examples\n\nfilter examples:\n\n```yaml\npolicies:\n- name: test-flavor\n  resource: openstack.flavor\n  filters:\n  - type: value\n    key: vcpus\n    value: 1\n    op: gt\n- name: test-project\n  resource: openstack.project\n  filters: []\n- name: test-server-image\n  resource: openstack.server\n  filters:\n  - type: image\n    image_name: cirros-0.5.1\n- name: test-user\n  resource: openstack.user\n  filters:\n  - type: role\n    project_name: demo\n    role_name: _member_\n    system_scope: false\n- name: test-server-flavor\n  resource: openstack.server\n  filters:\n  - type: flavor\n    vcpus: 1\n- name: test-server-age\n  resource: openstack.server\n  filters:\n  - type: age\n    op: lt\n    days: 1\n- name: test-server-tags\n  resource: openstack.server\n  filters:\n  - type: tags\n    tags:\n    - key: a\n      value: a\n    - key: b\n      value: c\n    op: any\n```\n",
    'long_description_content_type': 'text/markdown',
    'author': 'Cloud Custodian Project',
    'author_email': None,
    'maintainer': None,
    'maintainer_email': None,
    'url': 'https://cloudcustodian.io',
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
