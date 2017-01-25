Config - Custom Rules
=====================

Cloud Custodian is the easiest way to write and provision `custom AWS Config
rules
<http://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_develop-rules.html>`_.
In this doc we'll look at how we would deploy the :ref:`quickstart
<quickstart>` example using Config. Before you proceed, make sure you've
terminated any EC2 instance left over from the quickstart.

First, modify ``custodian.yml`` to specify a mode type of ``config-rule``:

.. code-block:: yaml

    policies:
      - name: my-first-policy
        mode:
            type: config-rule
        resource: ec2
        filters:
          - "tag:Custodian": present
        actions:
          - stop

You'll need one additional piece of information in order to deploy the policy:
the ARN of an IAM role to assume when running the Lambda that Custodian is
going to install for you. We specify this with an additional argument when
deploying the policy:

.. code-block:: bash

    custodian run -c custodian.yml -s . --assume=arn:aws:iam::123456789012:role/some-role

That should give you log output like this::

    2017-01-25 05:43:01,539: custodian.policy:INFO Provisioning policy lambda my-first-policy
    2017-01-25 05:43:04,683: custodian.lambda:INFO Publishing custodian policy lambda function custodian-my-first-policy

Go check the AWS console to see the Lambda as well as the Config rule that
Custodian created. The Config rule should be listed as "Compliant" or "No
results reported" (if not, be sure you terminated any instance left over from
the quickstart).

Now for the fun part! With your new policy installed, go ahead and create an
EC2 instance with a ``Custodian`` tag (any non-empty value), and wait (events
from Config are effectively delayed 15m up to 6hrs on tag changes). If all goes
well, you should eventually see that your new custom Config rule notices the
EC2 instance with the ``Custodian`` tag, and stops it according to your policy.

Congratulations! You have now installed your policy to run under Config rather
than from your command line.
