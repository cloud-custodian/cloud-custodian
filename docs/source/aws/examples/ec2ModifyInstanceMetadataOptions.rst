EC2 - Modify Instance Metadata Options
======================================

The following examples allow you to enforce Instance metadata options over EC2 instances.
to learn more about Instance Metadata option please visit: 
https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_ModifyInstanceMetadataOptions.html

To filter the list of instances you can choose any combination of EC2 metadata-instances elements.

 As of now below options are available:
 
  - HttpEndpoint

    - Valid Values: disabled | enabled
    - Action value: HttpEndpoint

  - HttpPutResponseHopLimit

    - Possible values: Integers from 1 to 64
    - Action value: HttpPutResponseHopLimit

  - HttpTokens

    - Valid Values: optional | required
    - Action value: tokens

  - InstanceMetadataTags

    - Valid Values: disabled | enabled
    - Action value: metadata-tags

Examples:
+++++++++

Require HttpTokens.

.. code-block:: yaml

   policies:
     - name: ec2-require-imdsv2
       resource: ec2
       description: |
         Finds all instances with optional HttpTokens and change the policy to Required.
       filters:
         - MetadataOptions.HttpTokens: optional
       actions:
         - type: set-metadata-access
           tokens: required


Disable the HttpEndpoint.

.. code-block:: yaml

   policies:
     - name: ec2-disable-imds
       resource: ec2
       description: |
        Finds all instances with enabled HttpEndpoint and change it to disabled.
        By default this option must be enabled therefore, please make sure before disabling this option.
       filters:
         - MetadataOptions.HttpEndpoint: enabled
       actions:
         - type: set-metadata-access
           endpoint: disabled


Enable the Instance Metadata Tags.

.. code-block:: yaml

   policies:
     - name: ec2-enable-imds
       resource: ec2
       description: |
        Finds all the instances with disables Instance Meta Data Tags and enable them.
       filters:
         - MetadataOptions.InstanceMetadataTags: disabled
       actions:
         - type: set-metadata-access
           metadata-tags: enabled


Instance MetaData Tags Reference: https://amzn.to/2XOuxpQ

Custodian Filters reference: https://cloud-custodian.github.io/cloud-custodian/docs/filters.html
