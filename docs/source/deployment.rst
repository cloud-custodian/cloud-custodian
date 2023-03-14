.. _deployment:

Deployment
==========

In this section we will cover a few different deployment options for
Cloud Custodian.

.. _compliance_as_code:

Compliance as Code
------------------
When operating Cloud Custodian, it is highly recommended to treat the policy
files as code, similar to that of Terraform or CloudFormation files. Cloud
Custodian has a built-in dryrun mode and policy syntax validation which when
paired with an automated CI system, can help you release policies with confidence.

This tutorial assumes that you have working knowledge of Github, Git, Docker,
and a continuous integration tool (Jenkins, Drone, Travis, etc.).

To begin, start by checking your policy files into a source control management
tool like Github. This allows us to version and enable collaboration through
git pull requests and issues. In this example, we will be setting up a new repo
in Github.

First, set up a new repo in Github and grab the repository url. You don't need
to add a README or any other files to it first.

.. code-block:: bash

    mkdir my-policies
    cd my-policies
    git init
    git remote add origin <github repo url>
    touch policy.yml

Next, we'll add a policy to our new ``policy.yml`` file.

.. code-block:: yaml

    policies:
      - name: aws-vpcs
        resource: aws.vpc

Once you've added the policy to your policy file we can stage our changes from our
working directory and push it up to our remote:

.. code-block:: bash

    # this should show your policy.yml as an untracked file
    git status

    git add policy.yml
    git commit -m 'init my first policy'
    git push -u origin master

Once you've pushed your changes you should be able to see your new changes inside
of Github. Congratulations, you're now ready to start automatically validating and
testing your policies!

.. _continuous_integration_of_policies:

Continuous Integration of Policies
----------------------------------

Next, enable a CI webhook back to your CI system of choice when pull requests
targeting your master branch are opened or updated. This allows us to continuously
test and validate the policies that are being modified.

In this example, we will be using Microsoft Azure Devops Pipelines.

First, navigate to https://azure.microsoft.com/en-us/services/devops/pipelines/ and
click the "Start pipelines free with Github" button and follow the flow to connect
your Github account with Devops Pipelines.

Next click on the Pipelines section in the left hand side of the sidebar and connect
with Github. Once the pipeline is setup, we can add the following azure devops
configuration to our repo:

.. code-block:: yaml

    trigger:
    - master

    jobs:
      - job: 'Validate'
        pool:
          vmImage: 'Ubuntu-16.04'
        steps:
          - checkout: self
          - task: UsePythonVersion@0
            displayName: "Set Python Version"
            inputs:
              versionSpec: '3.7'
              architecture: 'x64'
          - script: pip install --upgrade pip
            displayName: Upgrade pip
          - script: pip install c7n c7n_azure c7n_gcp
            displayName: Install custodian
          - script: custodian validate policy.yml
            displayName: Validate policy file

This configuration will install Cloud Custodian and validate the policy.yml file
that we created in the previous step.

Finally, we can run the new policies against your cloud environment in dryrun mode.
This mode will only query the resources and apply the filters on the resources. Doing
this allows you to assess the potential blast radius of a given policy change.

Setting up the automated dryrun of policies is left as an exercise to the user-- this
requires hosting your cloud authentication tokens inside of a CI system or hosting your
own CI system and using Managed Service Identities (Azure) or Instance Profiles (AWS).

It's important to verify that the results of the dryrun match your expectations. Custodian
is a very powerful tool that will do exactly what you tell it to do! In this case, you should
always "measure twice, cut once".

.. _iam_setup:

IAM Setup
---------

To run Cloud Custodian against your account, you will need an IAM role with appropriate
permissions. Depending on the scope of the policy, these permissions may differ from policy
to policy. For a baseline, the managed read only policies in each of the respective cloud
providers will be enough to dryrun your policies. Actions will require additional IAM
permissions which should be added at your discretion.

For serverless policies, Custodian will need the corresponding permissions to provision
serverless functions.

In AWS, you will need ReadOnly access as well as the following permissions:

.. code-block:: json

    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "CustodianLambdaPermissions",
                "Effect": "Allow",
                "Action": [
                    "cloudwatch:PutMetricData",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DeleteNetworkInterface",
                    "ec2:CreateNetworkInterface",
                    "events:PutRule",
                    "events:PutTargets",
                    "iam:PassRole",
                    "lambda:CreateFunction",
                    "lambda:TagResource",
                    "lambda:CreateEventSourceMapping",
                    "lambda:UntagResource",
                    "lambda:PutFunctionConcurrency",
                    "lambda:DeleteFunction",
                    "lambda:UpdateEventSourceMapping",
                    "lambda:InvokeFunction",
                    "lambda:UpdateFunctionConfiguration",
                    "lambda:UpdateAlias",
                    "lambda:UpdateFunctionCode",
                    "lambda:AddPermission",
                    "lambda:DeleteAlias",
                    "lambda:DeleteFunctionConcurrency",
                    "lambda:DeleteEventSourceMapping",
                    "lambda:RemovePermission",
                    "lambda:CreateAlias",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:CreateLogGroup"
                ],
                "Resource": "*"
            }
        ]
    }

Note: These are just the permissions to deploy Custodian Lambda functions, these are not
the permissions that are required to run Custodian _in_ the Lambda function. Those roles
are defined in the role attribute in the policy or with the assume role used in the cli.


.. _single_node_usage:

Single Node Deployment
----------------------

Now that your policies are stored and available in source control, you can now
fill in the next pieces of the puzzle to deploy. The simplest way to operate
Cloud Custodian is to start with running Cloud Custodian against a single account (or subscription or project) on a virtual machine.

To start, create a virtual machine on your cloud provider of choice.
It's recommended to execute Cloud Custodian in the same cloud provider
that you are operating against to prevent a hard dependency on one
cloud to another as well being able to utilize your cloud's best practices
for credentials (instance profile, service account, etc).

Then, log into the instance and set up Custodian, following the instructions
in the  :ref:`install-cc` guide.

Once you have Cloud Custodian installed, download your policies that you created
in the :ref:`compliance_as_code` section. If using git, just simply do a ``git clone``::

    git clone <repository-url>

You now have your policies and custodian available on the instance. Typically, policies
that query the extant resources in the account/project/subscription should be run
on a regular basis to ensure that resources are constantly compliant. To do this you
can simply set up a cron job to run custodian on a set cadence.

.. _monitoring_custodian:

Monitoring Cloud Custodian
--------------------------

Cloud Custodian ships with the ability to emit metrics on policy execution and transport
logs to cloud provider native logging solutions.

When executing Custodian, you can enable metrics simply by adding the ``-m`` flag and the
cloud provider::

  # AWS
  custodian run -s output -m aws policy.yml

  # Azure
  custodian run -s output -m azure policy.yml

  # GCP
  custodian run -s output -m gcp policy.yml

When you enable metrics, a new namespace will be created and the following metrics will be
recorded there:

- ResourceCount
- ResourceTime
- ActionTime

To enable logging to CloudWatch logs, Stackdriver, or Azure AppInsights, use the ``-l`` flag::

  # AWS CloudWatch Logs
  custodian run -s output -l /cloud-custodian/policies policy.yml

  # Azure App Insights Logs
  custodian run -s output -l azure://cloud-custodian/policies policy.yml

  # Stackdriver Logs
  custodian run -s output -l gcp://cloud-custodian/policies policy.yml

You can also store the output of your Custodian logs in a cloud provider's blob storage like S3
or Azure Storage accounts::

  # AWS S3
  custodian run -s s3://my-custodian-bucket policy.yml

  # Azure Storage Accounts
  custodian run -s azure://my-custodian-storage-account policy.yml

.. _mailer_and_notifications_deployment:

Mailer and Notifications Deployment
-----------------------------------

For instructions on how to deploy the mailer for notifications, see :doc:`/tools/c7n-mailer`

.. _multi_account_execution:

Multi Account Execution
-----------------------

For more advanced setups, such as executing Custodian against multiple accounts, we
distribute the tool c7n-org. c7n-org utilizes a accounts configuration file and
assume roles to operate against multiple accounts, projects, or subscriptions in
parallel. More information can be found in :doc:`/tools/c7n-org`.


.. _advanced_continuous_integration_tips:

Advanced Continuous Integration Tips
------------------------------------

When policy files reach a sufficiently large size it can cause dryruns to execute for a
significantly long period of time. In most cases, the only thing that actually needs
to be tested would be the policies that were changed.

The following example will download the cloudcustodian/policystream image and
generate a policy file containing only the policies that changed between the most
recent commit and master.

.. code-block:: bash

    # in your git directory for policies
    docker pull cloudcustodian/policystream
    docker run -v $(pwd):/home/custodian/policies cloudcustodian > policystream-diff.yml
    custodian run -s output -v --dryrun policystream-diff.yml

After running your new policy file (policystream-diff.yml), the outputs will be stored
in the output directory.


.. _additional_resources:

Additional Resources
--------------------

- `manheim-c7n-tools <https://github.com/manheim/manheim-c7n-tools>`_ - Manheim's Cloud
  Custodian (c7n) wrapper package, policy generator/interpolator, runner, error scanner,
  and supporting tools.
