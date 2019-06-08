.. _filters:

Generic Filters
===============

The following filters can be applied to all policies for all resources. See the
:ref:`Filters and Actions reference <policy>` for
aws resource-specific filters.

Value Filter
-------------

Cloud Custodian provides for a flexible query language on any resource by
allowing for rich queries on JSON objects via JMESPath, and allows for
mixing and combining those with boolean conditional operators that
are nest-able. (Tutorial here on `JMESPath <http://jmespath.org/tutorial.html>`_ syntax)


The base value filter enables the use of jmespath with data returned from a describe call.

.. code-block:: yaml

    filters:
         - type: value
           key: "State[0]"    ─▶ The value from the describe call
           value: "running"   ─▶ Value that is being filtered against


There are several ways to get a list of possible keys for each resource.

- Via Custodian CLI

    Create a new custodian yaml file with just the name and resource fields. Then run
    ``custodian run -s OUTPUT_DIR``. The valid key fields can be found in the output directory
    in resources.json

    .. code-block:: yaml

        policies:
          - name: my-first-policy
            resource: aws.ec2

- Via Cloud Providers CLI

    Use the relevant cloud provider cli to run the describe call to view all available keys. For example
    using aws cli run ``aws ec2 describe-instances`` or with azure ``az vm list``.

    Note: You do not need to include the outermost json field in most cases since custodian removes this field
    from the results.

- Via Cloud Provider Documentation

    Go to the relevant cloud provider sdk documentation and search for the describe api call for the resource
    you're interested in. The available fields will be listed under the results of that api call.



- Comparison operators:
    The generic value filter allows for comparison operators to be used

    - ``equal`` or ``eq``
    - ``not-equal`` or ``ne``
    - ``greater-than`` or ``gt``
    - ``gte`` or ``ge``
    - ``less-than`` or ``lt``
    - ``lte`` or ``le``

  .. code-block:: yaml

      filters:
         - type: value
           key: CpuOptions.CoreCount      ─▶ The value from the describe call
           value: 36                      ─▶ Value that is being compared
           op: greater-than               ─▶ Comparison Operator

- Other operators:
    - ``absent``
    - ``present``
    - ``not-null``
    - ``empty``
    - ``contains``

  .. code-block:: yaml

      filters:
         - type: value
           key: CpuOptions.CoreCount      ─▶ The value from the describe call
           value: present                 ─▶ Checks if key is present


- Logical Operators:
    - ``or`` or ``Or``
    - ``and`` or ``And``
    - ``not``

  .. code-block:: yaml

      filters:
         - or:                              ─▶ Logical Operator
           - type: value
             key: CpuOptions.CoreCount      ─▶ The value from the describe call
             value: 36                      ─▶ Value that is being compared
           - type: value
             key: CpuOptions.CoreCount      ─▶ The value from the describe call
             value: 42                      ─▶ Value that is being compared

- List Operators:
    There is a collection of operators that can be used with user supplied lists. The operators
    are evaluated as ``value from key`` in (the operator) ``given value``. If you would like it
    evaluated in the opposite way  ``given value`` in (the operator) ``value from key`` then you
    can include the ``swap`` transformation or use the ``contains`` operator.

    - ``in``
    - ``not-in`` or ``ni``
    - ``intersect`` - Provides comparison between 2 lists


  .. code-block:: yaml

      filters:
         - type: value
           key: ImageId                   ─▶ The value from the describe call
           op: in                         ─▶ List operator
           value: [ID-123, ID-321]        ─▶ List of Values to be compared against

  .. code-block:: yaml

      filters:
         - type: value
           key: ImageId.List              ─▶ The value from the describe call
           op: in                         ─▶ List operator
           value: ID-321                  ─▶ Values to be compared against
           value_type: swap               ─▶ Switches list comparison order



- Special operators:
    - ``glob`` - Provides Glob matching support
    - ``regex`` - Provides Regex matching support but ignores case
    - ``regex-case`` - Provides case sensitive Regex matching support


  .. code-block:: yaml

      filters:
         - type: value
           key: FunctionName                ─▶ The value from the describe call
           op: regex                        ─▶ Special operator
           value: ^(custodian?)\w+          ─▶ Regex string


- Transformations:
  Transformations on the value can be done using the ``value_type`` keyword.  The
  following value types are supported:

  - ``age`` - convert to a datetime (for past date comparisons)
  - ``cidr`` - parse an ipaddress
  - ``cidr_size`` - the length of the network prefix
  - ``expiration`` - convert to a datetime (for future date comparisons)
  - ``integer`` - convert the value to an integer
  - ``normalize`` - convert the value to lowercase
  - ``resource_count`` - compare against the number of matched resources
  - ``size`` - the length of an element
  - ``swap`` - swap the value and the evaluated key
  - ``date`` - parse the filter's value as a date.


  Examples:

  .. code-block:: yaml

     # Get the size of a group
     - type: value
       key: SecurityGroups[].GroupId
       value_type: size
       value: 2

     # Membership example using swap
     - type: value
       key: SecurityGroups[].GroupId
       value_type: swap
       op: in
       value: sg-49b87f44

     # Convert to integer before comparison
     - type: value
       key: tag:Count
       op: greater-than
       value_type: integer
       value: 0

     # Apply only to rds instances created after the given date
     - type: value
       key: InstanceCreateTime
       op: greater-than
       value_type: date
       value: "2019/05/01"

     # Find instances launched within the last 31 days
     - type: value
       key: LaunchTime
       op: less-than
       value_type: age
       value: 32

     # Use `resource_count` to filter resources based on the number that matched
     # Note that no `key` is used for this value_type since it is matching on
     # the size of the list of resources and not a specific field.
     - type: value
       value_type: resource_count
       op: lt
       value: 2

      # This policy will use `intersect` op to compare rds instances subnet group list
      # against a user provided list of public subnets from a s3 txt file.
      - name: find-rds-on-public-subnets-using-s3-list
        comment:  |
           The txt file needs to be in utf-8 no BOM format and contain one
           subnet per line in the file no quotes around the subnets either.
        resource: aws.rds
        filters:
            - type: value
              key: "DBSubnetGroup.Subnets[].SubnetIdentifier"
              op: intersect
              value_from:
                  url: s3://cloud-custodian-bucket/PublicSubnets.txt
                  format: txt

     # This policy will compare rds instances subnet group list against a
     # inline user provided list of public subnets.
     - name: find-rds-on-public-subnets-using-inline-list
       resource: aws.rds
       filters:
           - type: value
             key: "DBSubnetGroup.Subnets[].SubnetIdentifier"
             op: intersect
             value:
                 - subnet-2a8374658
                 - subnet-1b8474522
                 - subnet-2d2736444

- Value Regex:

  When using a Value Filter, a ``value_regex`` can be
  specified. This will mean that the value used for comparison is the output
  from evaluating a regex on the value found on a resource using `key`.

  The filter expects that there will be exactly one capturing group, however
  non-capturing groups can be specified as well, e.g. ``(?:newkey|oldkey)``.

  Note that if the value regex does not find a match, it will return a ``None``
  value.

  In this example there is an ``expiration`` comparison,
  which needs a datetime, however the tag containing this information
  also has other data in it. By setting the ``value_regex``
  to capture just the datetime part of the tag, the filter can be evaluated
  as normal.

  .. code-block:: yaml

    # Find expiry from tag contents
    - type: value
      key: "tag:metadata"
      value_type: expiration
      value_regex: ".*delete_after=([0-9]{4}-[0-9]{2}-[0-9]{2}).*"
      op: less-than
      value: 0

Age Filter
-------------
  Automatically filter resources older than a given date in Days (see `Dateutil Parser <http://dateutil.readthedocs.org/en/latest/parser.html#dateutil.parser.parse>`_)
  These are implemented on a per resource basis. See the :ref:`Resource-Specific Filters and Actions reference <policy>` for
  resource-specific filters.

  Generally you should use a value filter instead of an age filter, as it supports doing age/expiration comparisons on
  any date attribute.


Event Filter
-------------
  Filter against a CloudWatch event JSON associated to a resource type. The list of possible keys are now from the cloudtrail
  event and not the describe resource call as is the case in the ValueFilter

  .. code-block:: yaml

     - name: no-ec2-public-ips
       resource: aws.ec2
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
