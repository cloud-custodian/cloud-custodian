.. _filters:

Generic Filters
===============

These filters can be applied to all policies for all resources. See the
:ref:`Resource-Specific Filters and Actions reference <policy>` for
resource-specific filters.

Value Filters
-------------

Cloud Custodian provides for a flexible query language on any resource by
allowing for rich queries on JSON objects via JMESPath, and allows for
mixing and combining those with a boolean conditional operators that
are nest-able. Comparison between values is configurable supporting
scalar operators:

- Comparison operators:
    - ``equal`` or ``eq``
    - ``not-equal`` or ``ne``
    - ``greater-than`` or ``gt``
    - ``gte`` or ``ge``
    - ``less-than`` or ``lt``
    - ``lte`` or ``le``
- Other operators
    - ``absent``
    - ``present``
    - ``not-null``
    - ``empty``
- Collection operators against user supplied lists:
    - ``in``
    - ``not-in`` or ``ni``
    - ``or`` or ``Or``
    - ``and`` or ``And``
    - ``not``
- Special operators:
    - ``glob`` - Provides Glob matching support
    - ``regex`` - Provides Regex matching support but ignores case

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
