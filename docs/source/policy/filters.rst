.. _filters:

Value Filters
-------------

Cloud Custodian provides for a flexible query language on any resource by
allowing for rich queries on JSON objects via JMESPath, and allows for
mixing and combining those with a boolean conditional operators that
are nest-able. Comparison between values is configurable supporting
scalar operators:

- ``absent``
- ``not-null``
- ``equal`` or ``eq``
- ``not-equal`` or ``ne``
- ``greater-than`` or ``gt``
- ``gte`` or ``ge``
- ``less-than`` or ``lt``
- ``lte`` or ``le``
- collection operators against user supplied lists:
    - ``in``
    - ``not-in`` or ``ni``
    - ``or`` or ``Or``
    - ``and`` or ``And``
- `glob` - Provides Glob matching support
- `regex` - Provides Regex matching support but ignores case

`AgeFilter`
  Automatically filter resources older than a given date in Days (see `Dateutil Parser <http://dateutil.readthedocs.org/en/latest/parser.html#dateutil.parser.parse>`_)


JMESPath Filter
---------------

`ValueFilter`
  Generic value filter using jmespath based on the data returned from a describe call

  .. code-block:: yaml

     - name: ebs-unmark-attached-deletion
       resource: ebs
       comments: |
         Unmark any attached EBS volumes that were scheduled for deletion
         if they are now attached
       filters:
         - type: value                     ─┐ The value of the key from the describe
           key: "Attachments[0].Device"     ├▶EBS call
           value: not-null                 ─┘
         - "tag:maid_status": not-null     ─▶ This filter
       actions:
         - unmark


`EventFilter`
  Filter against a CloudWatch event JSON associated to a resource type

  .. code-block:: yaml

     - name: no-ec2-public-ips
       resource: ec2
       mode:
         type: cloudtrail
         events:
             - RunInstances
       filters:
         - type: event                                                                           ─┐ The key is a JMESPath Query of
           key: "detail.requestParameters.networkInterfaceSet.items[].associatePublicIpAddress"   ├▶the event JSON from CloudWatch
           value: true                                                                           ─┘
       actions:
         - type: terminate
           force: true
