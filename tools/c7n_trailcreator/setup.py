# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_trailcreator']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (>=2.0.0,<3.0.0)',
 'attrs (>=22.1.0,<23.0.0)',
 'boto3 (>=1.24.44,<2.0.0)',
 'botocore (>=1.27.44,<2.0.0)',
 'c7n (>=0.9.18,<0.10.0)',
 'c7n-org (>=0.6.17,<0.7.0)',
 'click (>=8.1.3,<9.0.0)',
 'click>=8.0,<9.0',
 'colorama (>=0.4.5,<0.5.0)',
 'docutils (>=0.17.1,<0.18.0)',
 'importlib-metadata (>=4.12.0,<5.0.0)',
 'importlib-resources (>=5.9.0,<6.0.0)',
 'jmespath (>=1.0.1,<2.0.0)',
 'jsonschema (>=4.9.0,<5.0.0)',
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

entry_points = \
{'console_scripts': ['c7n-trailcreator = c7n_trailcreator.trailcreator:cli']}

setup_kwargs = {
    'name': 'c7n-trailcreator',
    'version': '0.2.17',
    'description': 'Cloud Custodian - Retroactive Tag Resource Creators from CloudTrail',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': '# c7n-trailcreator:  Retroactive Resource Creator Tagging\n\nThis script will process cloudtrail records to create a sqlite db of\nresources and their creators, and then use that sqlitedb to tag\nthe resources with their creator\'s name.\n\nIn processing cloudtrail it can use either Athena or S3 Select. A\nconfig file of the events and resources of interest is required.\n\n## Install\n\n```shell\n$ pip install c7n_trailcreator\n\n$ c7n-trailcreator --help\n```\n\n## Config File\n\nThe config file format here is similiar to what custodian requires\nfor lambda policies on cloudtrail api events as an event selector.\n\nFirst for each resource, the custodian resource-type is required\nto be specified, and then for each event, we need to know the\nname of the service, the event name, and a jmespath expression\nto get the resource ids.\n\nHere\'s a a few examples, covering iam-user, iam-role, and and an s3 bucket.\n\n\n```json\n{\n  "resources": [\n    {\n      "resource": "iam-role",\n      "events": [\n        {\n          "event": "CreateRole",\n          "ids": "requestParameters.roleName",\n          "service": "iam.amazonaws.com"\n        }\n      ]\n    },\n    {\n      "resource": "s3",\n      "events": [\n        {\n          "ids": "requestParameters.bucketName",\n          "event": "CreateBucket",\n          "service": "s3.amazonaws.com"\n        }\n      ]\n    },\n    {\n      "resource": "iam-user",\n      "events": [\n        {\n          "event": "CreateUser",\n          "ids": "requestParameters.userName",\n          "service": "iam.amazonaws.com"\n        }\n      ]\n    }]\n}\n```\n\n## Athena Usage\n\nTrail creators supports loading data from s3 using s3 select or from cloudtrail s3 using athena.\n\nNote you\'ll have to pre-created the athena table for cloudtrail previously per\nhttps://docs.aws.amazon.com/athena/latest/ug/cloudtrail-logs.html\n\nLet\'s use the example config file to load up data for all the roles, buckets, and users created in 2019\n\n```\nc7n-trailcreator load-athena \\\n    --region us-east-1 \\\n\t--resource-map resource_map.json \\\n\t--table cloudtrail_logs_custodian_skunk_trails \\\n\t--db "creators.db" \\\n\t--year 2019\n```\n\nBy default we\'ll use the default s3 athena output used by the console,\nand the default db and primary workgroup, you can pass all of these in\non the cli to be more explicit.\n\nYou can also specify to just process a month with `--month 2019/11` or\nan individual day with `--day 2019/02/01`\n\n```\nINFO:c7n_trailowner:Athena query:569712dc-d1e9-4474-b86f-6579c53b5b46\nINFO:c7n_trailowner:Polling athena query progress scanned:489.24 Mb qexec:28.62s\nINFO:c7n_trailowner:Polling athena query progress scanned:1.29 Gb qexec:88.96s\nINFO:c7n_trailowner:Polling athena query progress scanned:2.17 Gb qexec:141.16s\nINFO:c7n_trailowner:processing athena result page 78 records\nINFO:c7n_trailowner:Athena Processed 78 records\n```\n\nNote you can reprocess a completed query\'s results, by passing in `--query-id` on the cli.\n\n## Tagging\n\nIt supports this across all the resources that custodian supports.\n\n```\n$ c7n-trailcreator tag \\\n\t--db creators.db \\\n\t--creator-tag Owner \\\n\t--region us-east-1\nINFO:c7n_trailowner:account:644160558196 region:us-east-1 tag 13 iam-role resources users:5 population:97 not-found:84 records:124\nINFO:c7n_trailowner:account:644160558196 region:us-east-1 tag 5 iam-user resources users:4 population:6 not-found:1 records:18\nINFO:c7n_trailowner:account:644160558196 region:us-east-1 tag 9 s3 resources users:4 population:14 not-found:5 records:20\nINFO:c7n_trailowner:auto tag summary account:644160558196 region:us-east-1\n iam-role-not-found: 84\n iam-role: 13\n iam-user-not-found: 1\n iam-user: 5\n s3-not-found: 5\n s3: 9\nINFO:c7n_trailowner:Total resources tagged: 27\n```\n\nlet\'s break down one of these log messages\n\n```\nINFO:c7n_trailowner:account:644160558196 region:us-east-1 tag 13 iam-role resources users:5 population:97 not-found:84 records:124\n```\n\n- records: the count of database create events we have for this resource type.\n- users: the number of unique users for whom we have create events.\n- not-found: the number of resources for whom we do not have create events, ie created before or after our trail analysis period.\n- population: the total number of resources in the account region.\n\n## Multi Account / Multi Region\n\nc7n-trailcreator supports executing across multiple accounts and regions when tagging\nusing the same file format that c7n-org uses to denote accounts. See `tag-org` subcommand.\n\n',
    'long_description_content_type': 'text/markdown',
    'author': 'Cloud Custodian Project',
    'author_email': None,
    'maintainer': None,
    'maintainer_email': None,
    'url': 'https://cloudcustodian.io',
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'entry_points': entry_points,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
