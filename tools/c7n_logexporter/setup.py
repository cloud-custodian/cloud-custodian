# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n_logexporter']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete (>=1.12.2,<2.0.0)',
 'attrs (>=20.3.0,<21.0.0)',
 'boto3 (>=1.17.10,<2.0.0)',
 'botocore (>=1.20.10,<2.0.0)',
 'c7n (>=0.9.11,<0.10.0)',
 'click>=7.0,<8.0',
 'importlib-metadata (>=3.4.0,<4.0.0)',
 'jmespath (>=0.10.0,<0.11.0)',
 'jsonpickle (>=1.3,<2.0)',
 'jsonschema (>=3.2.0,<4.0.0)',
 'pyrsistent (>=0.17.3,<0.18.0)',
 'python-dateutil (>=2.8.1,<3.0.0)',
 'pyyaml (>=5.4.1,<6.0.0)',
 's3transfer (>=0.3.4,<0.4.0)',
 'six (>=1.15.0,<2.0.0)',
 'tabulate (>=0.8.8,<0.9.0)',
 'typing-extensions (>=3.7.4.3,<4.0.0.0)',
 'urllib3 (>=1.26.3,<2.0.0)',
 'zipp (>=3.4.0,<4.0.0)']

entry_points = \
{'console_scripts': ['c7n-log-exporter = c7n_logexporter.exporter:cli']}

setup_kwargs = {
    'name': 'c7n-logexporter',
    'version': '0.4.10',
    'description': 'Cloud Custodian - Cloud Watch Log S3 exporter',
    'long_description': '# c7n-log-exporter: Cloud watch log exporter automation\n\nA small serverless app to archive cloud logs across accounts to an archive bucket. It utilizes\ncloud log export to s3 feature for historical exports.\n\nIt also supports kinesis streams / firehose to move to realtime exports in the same format\nas the periodic historical exports.\n\n\n## Features\n\n - Log group filtering by regex\n - Incremental support based on previously synced dates\n - Incremental support based on last log group write time\n - Cross account via sts role assume\n - Lambda and CLI support.\n - Day based log segmentation (output keys look\n   like $prefix/$account_id/$group/$year/$month/$day/$export_task_uuid/$stream/$log)\n \n\n## Assumptions\n\n - The archive bucket has already has appropriate bucket policy permissions.\n   For details see:\n   https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/S3ExportTasks.html#S3Permissions\n - Default periodicity for log group archival into s3 is daily.\n - Exporter is run with account credentials that have access to the archive s3 bucket.\n - Catch up archiving is not run in lambda (do a cli run first)\n\n\n## Cli usage\n\n```\nmake install\n```\n\nYou can run on a single account / log group via the export subcommand\n```\nc7n-log-exporter export --help\n```\n\n## Config format\n\nTo ease usage when running across multiple accounts, a config file can be specified, as\nan example.\n\n```\ndestination:\n  bucket: custodian-log-archive\n  prefix: logs2\n\naccounts:\n  - name: custodian-demo\n    role: "arn:aws:iam::111111111111:role/CloudCustodianRole"\n    groups:\n      - "/aws/lambda/*"\n      - "vpc-flow-logs"\n```\n\n## Multiple accounts via cli\n\nTo run on the cli across multiple accounts, edit the config.yml to specify multiple\naccounts and log groups.\n\n```\nc7n-log-exporter run --config config.yml\n```\n\n## Serverless Usage\n\nEdit config.yml to specify the accounts, archive bucket, and log groups you want to\nuse.\n\n```\nmake install\nmake deploy\n```\n\n',
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
    'python_requires': '>=3.6,<4.0',
}


setup(**setup_kwargs)
