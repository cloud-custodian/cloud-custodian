# Automatically generated from poetry/pyproject.toml
# flake8: noqa
# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['c7n',
 'c7n.actions',
 'c7n.filters',
 'c7n.reports',
 'c7n.resources',
 'c7n.ufuncs']

package_data = \
{'': ['*']}

install_requires = \
['argcomplete>=1.12.3',
 'boto3>=1.12.31,<2.0.0',
 'docutils>=0.14,<0.18',
 'importlib-metadata>=4.11.1',
 'jsonschema>=3.0.0',
 'python-dateutil>=2.8.2,<3.0.0',
 'pyyaml>=5.4.0',
 'tabulate>=0.8.6,<0.9.0']

entry_points = \
{'console_scripts': ['custodian = c7n.cli:main']}

setup_kwargs = {
    'name': 'c7n',
    'version': '0.9.19',
    'description': 'Cloud Custodian - Policy Rules Engine',
    'license': 'Apache-2.0',
    'classifiers': [
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing'
    ],
    'long_description': 'Cloud Custodian\n=================\n\n<p align="center"><img src="https://cloudcustodian.io/img/logo_capone_devex_cloud_custodian.svg" alt="Cloud Custodian Logo" width="200px" height="200px" /></p>\n\n---\n\n[![](https://badges.gitter.im/cloud-custodian/cloud-custodian.svg)](https://gitter.im/cloud-custodian/cloud-custodian?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)\n[![CI](https://github.com/cloud-custodian/cloud-custodian/workflows/CI/badge.svg?event=push)](https://github.com/cloud-custodian/cloud-custodian/actions?query=workflow%3ACI+branch%3Amaster+event%3Apush)\n[![](https://dev.azure.com/cloud-custodian/cloud-custodian/_apis/build/status/Custodian%20-%20CI?branchName=master)](https://dev.azure.com/cloud-custodian/cloud-custodian/_build)\n[![](https://img.shields.io/badge/license-Apache%202-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)\n[![](https://codecov.io/gh/cloud-custodian/cloud-custodian/branch/master/graph/badge.svg)](https://codecov.io/gh/cloud-custodian/cloud-custodian)\n[![](https://requires.io/github/cloud-custodian/cloud-custodian/requirements.svg?branch=master)](https://requires.io/github/cloud-custodian/cloud-custodian/requirements/?branch=master)\n[![CII Best Practices](https://bestpractices.coreinfrastructure.org/projects/3402/badge)](https://bestpractices.coreinfrastructure.org/projects/3402)\n\nCloud Custodian is a rules engine for managing public cloud accounts and\nresources. It allows users to define policies to enable a well managed\ncloud infrastructure, that\\\'s both secure and cost optimized. It\nconsolidates many of the adhoc scripts organizations have into a\nlightweight and flexible tool, with unified metrics and reporting.\n\nCustodian can be used to manage AWS, Azure, and GCP environments by\nensuring real time compliance to security policies (like encryption and\naccess requirements), tag policies, and cost management via garbage\ncollection of unused resources and off-hours resource management.\n\nCustodian policies are written in simple YAML configuration files that\nenable users to specify policies on a resource type (EC2, ASG, Redshift,\nCosmosDB, PubSub Topic) and are constructed from a vocabulary of filters\nand actions.\n\nIt integrates with the cloud native serverless capabilities of each\nprovider to provide for real time enforcement of policies with builtin\nprovisioning. Or it can be run as a simple cron job on a server to\nexecute against large existing fleets.\n\nCloud Custodian is a CNCF Sandbox project, lead by a community of hundreds\nof contributors.\n\nFeatures\n--------\n\n-   Comprehensive support for public cloud services and resources with a\n    rich library of actions and filters to build policies with.\n-   Supports arbitrary filtering on resources with nested boolean\n    conditions.\n-   Dry run any policy to see what it would do.\n-   Automatically provisions serverless functions and event sources (\n    AWS CloudWatchEvents, AWS Config Rules, Azure EventGrid, GCP\n    AuditLog & Pub/Sub, etc)\n-   Cloud provider native metrics outputs on resources that matched a\n    policy\n-   Structured outputs into cloud native object storage of which\n    resources matched a policy.\n-   Intelligent cache usage to minimize api calls.\n-   Supports multi-account/subscription/project usage.\n-   Battle-tested - in production on some very large cloud environments.\n\nLinks\n-----\n\n-   [Homepage](http://cloudcustodian.io)\n-   [Docs](http://cloudcustodian.io/docs/index.html)\n-   [Project Roadmap](https://github.com/orgs/cloud-custodian/projects/1)\n-   [Developer Install](https://cloudcustodian.io/docs/developer/installing.html)\n-   [Presentations](https://www.google.com/search?q=cloud+custodian&source=lnms&tbm=vid)\n\nQuick Install\n-------------\n\n```shell\n$ python3 -m venv custodian\n$ source custodian/bin/activate\n(custodian) $ pip install c7n\n```\n\n\nUsage\n-----\n\nThe first step to using Cloud Custodian is writing a YAML file\ncontaining the policies that you want to run. Each policy specifies\nthe resource type that the policy will run on, a set of filters which\ncontrol resources will be affected by this policy, actions which the policy\nwith take on the matched resources, and a mode which controls which\nhow the policy will execute.\n\nThe best getting started guides are the cloud provider specific tutorials.\n\n - [AWS Getting Started](https://cloudcustodian.io/docs/aws/gettingstarted.html)\n - [Azure Getting Started](https://cloudcustodian.io/docs/azure/gettingstarted.html)\n - [GCP Getting Started](https://cloudcustodian.io/docs/gcp/gettingstarted.html)\n\nAs a quick walk through, below are some sample policies for AWS resources.\n\n  1. will enforce that no S3 buckets have cross-account access enabled.\n  1. will terminate any newly launched EC2 instance that do not have an encrypted EBS volume.\n  1. will tag any EC2 instance that does not have the follow tags\n     "Environment", "AppId", and either "OwnerContact" or "DeptID" to\n     be stopped in four days.\n\n```yaml\npolicies:\n - name: s3-cross-account\n   description: |\n     Checks S3 for buckets with cross-account access and\n     removes the cross-account access.\n   resource: aws.s3\n   region: us-east-1\n   filters:\n     - type: cross-account\n   actions:\n     - type: remove-statements\n       statement_ids: matched\n\n - name: ec2-require-non-public-and-encrypted-volumes\n   resource: aws.ec2\n   description: |\n    Provision a lambda and cloud watch event target\n    that looks at all new instances and terminates those with\n    unencrypted volumes.\n   mode:\n    type: cloudtrail\n    role: CloudCustodian-QuickStart\n    events:\n      - RunInstances\n   filters:\n    - type: ebs\n      key: Encrypted\n      value: false\n   actions:\n    - terminate\n\n - name: tag-compliance\n   resource: aws.ec2\n   description: |\n     Schedule a resource that does not meet tag compliance policies to be stopped in four days. Note a separate policy using the`marked-for-op` filter is required to actually stop the instances after four days.\n   filters:\n    - State.Name: running\n    - "tag:Environment": absent\n    - "tag:AppId": absent\n    - or:\n      - "tag:OwnerContact": absent\n      - "tag:DeptID": absent\n   actions:\n    - type: mark-for-op\n      op: stop\n      days: 4\n```\n\nYou can validate, test, and run Cloud Custodian with the example policy with these commands:\n\n```shell\n# Validate the configuration (note this happens by default on run)\n$ custodian validate policy.yml\n\n# Dryrun on the policies (no actions executed) to see what resources\n# match each policy.\n$ custodian run --dryrun -s out policy.yml\n\n# Run the policy\n$ custodian run -s out policy.yml\n```\n\nYou can run Cloud Custodian via Docker as well:\n\n```shell\n# Download the image\n$ docker pull cloudcustodian/c7n\n$ mkdir output\n\n# Run the policy\n#\n# This will run the policy using only the environment variables for authentication\n$ docker run -it \\\n  -v $(pwd)/output:/home/custodian/output \\\n  -v $(pwd)/policy.yml:/home/custodian/policy.yml \\\n  --env-file <(env | grep "^AWS\\|^AZURE\\|^GOOGLE") \\\n  cloudcustodian/c7n run -v -s /home/custodian/output /home/custodian/policy.yml\n\n# Run the policy (using AWS\'s generated credentials from STS)\n#\n# NOTE: We mount the ``.aws/credentials`` and ``.aws/config`` directories to\n# the docker container to support authentication to AWS using the same credentials\n# credentials that are available to the local user if authenticating with STS.\n\n$ docker run -it \\\n  -v $(pwd)/output:/home/custodian/output \\\n  -v $(pwd)/policy.yml:/home/custodian/policy.yml \\\n  -v $(cd ~ && pwd)/.aws/credentials:/home/custodian/.aws/credentials \\\n  -v $(cd ~ && pwd)/.aws/config:/home/custodian/.aws/config \\\n  --env-file <(env | grep "^AWS") \\\n  cloudcustodian/c7n run -v -s /home/custodian/output /home/custodian/policy.yml\n```\n\nThe [custodian cask\ntool](https://cloudcustodian.io/docs/tools/cask.html) is a go binary\nthat provides a transparent front end to docker that mirors the regular\ncustodian cli, but automatically takes care of mounting volumes.\n\nConsult the documentation for additional information, or reach out on gitter.\n\nCloud Provider Specific Help\n----------------------------\n\nFor specific instructions for AWS, Azure, and GCP, visit the relevant getting started page.\n\n- [AWS](https://cloudcustodian.io/docs/aws/gettingstarted.html)\n- [Azure](https://cloudcustodian.io/docs/azure/gettingstarted.html)\n- [GCP](https://cloudcustodian.io/docs/gcp/gettingstarted.html)\n\nGet Involved\n------------\n\n-   [GitHub](https://github.com/cloud-custodian/cloud-custodian) - (This page)\n-   [Slack](https://communityinviter.com/apps/cloud-custodian/c7n-chat) - Real time chat if you\'re looking for help or interested in contributing to Custodian! \n    - [Gitter](https://gitter.im/cloud-custodian/cloud-custodian) - (Older real time chat, we\'re likely migrating away from this)\n-   [Mailing List](https://groups.google.com/forum/#!forum/cloud-custodian) - Our project mailing list, subscribe here for important project announcements, feel free to ask questions\n-   [Reddit](https://reddit.com/r/cloudcustodian) - Our subreddit\n-   [StackOverflow](https://stackoverflow.com/questions/tagged/cloudcustodian) - Q&A site for developers, we keep an eye on the `cloudcustodian` tag\n-   [YouTube Channel](https://www.youtube.com/channel/UCdeXCdFLluylWnFfS0-jbDA/) - We\'re working on adding tutorials and other useful information, as well as meeting videos\n\nCommunity Resources\n-------------------\n\nWe have a regular community meeting that is open to all users and developers of every skill level.\nJoining the [mailing list](https://groups.google.com/forum/#!forum/cloud-custodian) will automatically send you a meeting invite. \nSee the notes below for more technical information on joining the meeting. \n\n- [Community Meeting Videos](https://www.youtube.com/watch?v=qy250y0UT-4&list=PLJ2Un8H_N5uBeAAWK95SnWvm_AuNJ8q2x)\n- [Community Meeting Notes Archive](https://github.com/orgs/cloud-custodian/discussions/categories/announcements)\n- [Upcoming Community Events](https://cloudcustodian.io/events/)\n- [Cloud Custodian Annual Report 2021](https://github.com/cncf/toc/blob/main/reviews/2021-cloud-custodian-annual.md) - Annual health check provided to the CNCF outlining the health of the project\n\n\nAdditional Tools\n----------------\n\nThe Custodian project also develops and maintains a suite of additional\ntools here\n<https://github.com/cloud-custodian/cloud-custodian/tree/master/tools>:\n\n- [**_Org_:**](https://cloudcustodian.io/docs/tools/c7n-org.html) Multi-account policy execution.\n\n- [**_PolicyStream_:**](https://cloudcustodian.io/docs/tools/c7n-policystream.html) Git history as stream of logical policy changes.\n\n- [**_Salactus_:**](https://cloudcustodian.io/docs/tools/c7n-salactus.html) Scale out s3 scanning.\n\n- [**_Mailer_:**](https://cloudcustodian.io/docs/tools/c7n-mailer.html) A reference implementation of sending messages to users to notify them.\n\n- [**_Trail Creator_:**](https://cloudcustodian.io/docs/tools/c7n-trailcreator.html) Retroactive tagging of resources creators from CloudTrail\n\n- **_TrailDB_:** Cloudtrail indexing and time series generation for dashboarding.\n\n- [**_LogExporter_:**](https://cloudcustodian.io/docs/tools/c7n-logexporter.html) Cloud watch log exporting to s3\n\n- [**_Cask_:**](https://cloudcustodian.io/docs/tools/cask.html) Easy custodian exec via docker\n\n- [**_Guardian_:**](https://cloudcustodian.io/docs/tools/c7n-guardian.html) Automated multi-account Guard Duty setup\n\n- [**_Omni SSM_:**](https://cloudcustodian.io/docs/tools/omnissm.html) EC2 Systems Manager Automation\n\n- [**_Mugc_:**](https://github.com/cloud-custodian/cloud-custodian/tree/master/tools/ops#mugc) A utility used to clean up Cloud Custodian Lambda policies that are deployed in an AWS environment.\n\nContributing\n------------\n\nSee <https://cloudcustodian.io/docs/contribute.html>\n\nSecurity\n--------\n\nIf you\'ve found a security related issue, a vulnerability, or a\npotential vulnerability in Cloud Custodian please let the Cloud\n[Custodian Security Team](mailto:security@cloudcustodian.io) know with\nthe details of the vulnerability. We\'ll send a confirmation email to\nacknowledge your report, and we\'ll send an additional email when we\'ve\nidentified the issue positively or negatively.\n\nCode of Conduct\n---------------\n\nThis project adheres to the [CNCF Code of Conduct](https://github.com/cncf/foundation/blob/master/code-of-conduct.md)\n\nBy participating, you are expected to honor this code.\n\n',
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
