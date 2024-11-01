.. _filters:

Generic Filters
===============

The following filters can be applied to all policies for all resources. See the
provider specific resource reference for additional information.

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


Special Values
~~~~~~~~~~~~~~

    These meta-values can be used to test whether or not a resource contains a specific value, and if
    the value is empty.

    - ``absent``: matches when a key *does not* exist
    - ``present``: matches when a key *does* exist
    - ``empty``: matches when a value is false, empty, or missing
    - ``not-null``: matches when a value exists, and is not false or empty

    Consider an S3 bucket with this abbreviated set of attributes:

    .. code-block:: json

      {
        "Name": "my_bucket",
        "Versioning": {},
        "Tags": [{
          "Environment": "dev",
          "Owner": ""
        }]
      }

    All of the following filters would match this resource:

    .. code-block::

      filters:
        - "tag:Environment": "dev"
        - "tag:Environment": "not-null"
        - "tag:Environment": "present"
        - "tag:Owner": "empty"
        - "tag:Owner": "present"
        - "tag:Team": "empty"
        - "tag:Team": "absent"
        - "Versioning": "empty"
        - "Versioning": "present"
        - "Versioning.Status": "empty"
        - "Versioning.Status": "absent"


Comparison Operators
~~~~~~~~~~~~~~~~~~~~

    The generic value filter allows for comparison operators to be used

    - ``equal`` or ``eq``
    - ``not-equal`` or ``ne``
    - ``greater-than`` or ``gt``
    - ``gte`` or ``ge``
    - ``less-than`` or ``lt``
    - ``lte`` or ``le``
    - ``in``
    - ``not-in`` or ``ni``
    - ``contains``

  .. code-block:: yaml

      filters:
         - type: value
           key: CpuOptions.CoreCount      ─▶ The value from the describe call
           value: 36                      ─▶ Value that is being compared
           op: greater-than               ─▶ Comparison Operator


Logical Operators
~~~~~~~~~~~~~~~~~

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

List Operators
~~~~~~~~~~~~~~

    There is a collection of operators that can be used with user supplied lists. The operators
    are evaluated as ``value from key`` in (the operator) ``given value``. If you would like it
    evaluated in the opposite way  ``given value`` in (the operator) ``value from key`` then you
    can include the ``swap`` transformation or use the ``contains`` operator.

    - ``in``
    - ``not-in`` or ``ni``
    - ``contains``
    - ``intersect`` - Match if two lists share any elements
    - ``difference`` - Match if the first list has any values not in the second list

  This filter only matches resources whose ``ImageId`` property appears in a predefined list:

  .. code-block:: yaml

      filters:
         - type: value
           key: ImageId                   ─▶ The value from the describe call
           op: in                         ─▶ List operator
           value: [ID-123, ID-321]        ─▶ List of Values to be compared against

  Some resource properties are lists themselves. For example, EC2 instances can have
  multiple security groups. For the next few examples, assume the filters are evaluating
  three instances:

  =========  ===============================================
  Instance   Security Group Names
  =========  ===============================================
  instance1  default, common, custom
  instance2  common, custom, extra
  instance3  common
  =========  ===============================================

  This filter matches ``instance1``, whose security group list contains the ``default`` group:

  .. code-block:: yaml

      filters:
         - type: value
           key: SecurityGroups[].GroupName
           op: contains
           value: default

  The ``difference`` operator can find instances with security groups that don't appear in
  a predefined list. This filter matches ``instance1`` and ``instance2``, because ``default``
  and ``extra`` aren't in the list of expected security groups:

  .. code-block:: yaml

      filters:
         - type: value
           key: SecurityGroups[].GroupName
           op: difference
           value:
             - common
             - custom

  ``value_type: swap`` can invert that logic, checking to see if the predefined list has
  any values that don't appear on an instance. This filter matches ``instance3``, because
  it is missing the ``custom`` security group:

  .. code-block:: yaml

      filters:
         - type: value
           key: SecurityGroups[].GroupName
           op: difference
           value:
             - common
             - custom
           value_type: swap

Pattern Matching Operators
~~~~~~~~~~~~~~~~~~~~~~~~~~

    - ``glob`` - Provides Glob matching support
    - ``regex`` - Provides Regex matching support but ignores case (1)
    - ``regex-case`` - Provides case sensitive Regex matching support (1)


  .. code-block:: yaml

      filters:
         - type: value
           key: FunctionName                ─▶ The value from the describe call, or resources.json
           op: regex                        ─▶ Special operator
           value: '(custodian|c7n)_\w+'     ─▶ Regex string: match all values beginning with custodian_ or c7n_

         - type: value
           key: name                        ─▶ The value from the describe call, or resources.json
           op: regex                        ─▶ Special operator
           value: '^.*c7n.*$'               ─▶ Regex string: match all values containing c7n

         - type: value
           key: name                        ─▶ The value from the describe call, or resources.json
           op: regex                        ─▶ Special operator
           value: '^((?!c7n).)*$'           ─▶ Regex string: match all values not containing c7n

  1. These operators are implemented using ``re.match``. If a filter isn't working as expected take a look at the `re`__ documentation.

  __ https://docs.python.org/3/library/re.html#search-vs-match

Value Type Transformations
~~~~~~~~~~~~~~~~~~~~~~~~~~

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

  Note that the `age` and `expiration` transformations expect a value given as
  a number of days. Use a floating point value to match time periods shorter than
  a day.

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

     # Find instances launched within the past 12 hours
     - type: value
       key: LaunchTime
       op: less-than
       value_type: age
       value: 0.5

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

Additional JMESPath Functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Cloud Custodian supports additional custom JMESPath functions, including:

- ``split(seperator, input_string) -> list[str]``: takes 2 arguments, the seperator token
  as well as the input string. Returns a list of strings.

  .. code-block:: yaml

    policies:
      - name: copy-related-tag-with-split
        resource: aws.log-group
        filters:
          - type: value
            key: logGroupName
            value: "/aws/lambda/"
            op: in
            value_type: swap
        actions:
          - type: copy-related-tag
            resource: aws.lambda
            # split the log group's name to get the lambda function's name
            key: "split(`/`, logGroupName)[-1]"
            tags: "*"

- ``from_json(json_encoded_string) -> obj``: takes 1 argument, a json encoded string.
  Returns an json decoded value.


Value Regex
~~~~~~~~~~~

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

Value From
~~~~~~~~~~

  ``value_from`` allows the use of external values in the Value Filter

  .. autodoconly:: c7n.resolver.ValuesFrom

Value Path
~~~~~~~~~~

  Retrieve values using JMESPath.

  The filter expects that a properly formatted 'string' is passed
  containing a valid JMESPath. (Tutorial here on `JMESPath <http://jmespath.org/tutorial.html>`_ syntax)

  When using a Value Filter, a ``value_path`` can be specified.
  This means the value(s) the filter will compare against are
  calculated during the initialization of the filter.

  Note that this option only pulls properties of the resource
  currently being filtered.

  .. code-block:: yaml

     policies:
      - name: find-admins-with-user-roles
        resource: gcp.project
        filters:
          - type: iam-policy
            doc:
              key: bindings[?(role=='roles/admin')].members[]
              op: intersect
              value_path: bindings[?(role=='roles/user_access')].members[]

  The iam-policy uses the generic Value Filter implementation.
  This implementation allows for the comparison of two separate lists of values
  within the same resource.

List Item Filter
----------------

The ``list-item`` filter makes it easier to evaluate resource properties that contain
a list of values.

Example 1: AWS ECS Task Definitions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AWS ECS task definitions include a list of container definitions. This policy matches
a task definition if any of its container images reference an image from outside a given
account and region:

  .. code-block:: yaml

   policies:
    - name: find-task-def-not-using-registry
      resource: aws.ecs-task-definition
      filters:
        - not:
          - type: list-item
            key: containerDefinitions
            attrs:
              - not:
                - type: value
                  key: image
                  value: "${account_id}.dkr.ecr.us-east-2.amazonaws.com.*"
                  op: regex

That check is not possible with the ``value`` filter alone, because the ``regex``
operator cannot operate directly against a list.

Example 2: S3 Lifecycle Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

S3 buckets can have lifecycle policies that include multiple rules.
This policy matches buckets that are missing a rule for cleaning up
incomplete multipart uploads.

  .. code-block:: yaml

   policies:
    - name: s3-mpu-cleanup-not-configured
      resource: aws.s3
      filters:
        - not:
          - type: list-item
            key: Lifecycle.Rules[]
            attrs:
              - Status: Enabled
              - AbortIncompleteMultipartUpload.DaysAfterInitiation: not-null

Here the ``list-item`` filter ensures that we check a combination of multiple
properties for each individual lifecycle rule.

Event Filter
-------------

Filter against a CloudWatch event JSON associated to a resource type. The
list of possible keys are now from the cloudtrail event and not the
describe resource call as is the case in the ValueFilter

  .. code-block:: yaml
    policies:
     - name: no-ec2-public-ips
       resource: aws.ec2
       mode: make
         - type: cloudtrail
           events:
             - RunInstances
       filters:
         - type: event
           # The key is a JMESPath Query of the event JSON from CloudWatch.
           key: "detail.requestParameters.networkInterfaceSet.items[].associatePublicIpAddress"
           # The key expression returns a list. Combining "op: contains" with "value: true"
           # allows this filter to match if any network interface has a public IP address.
           op: contains
           value: true
       actions:
         - type: terminate
           force: true


Reduce Filter
-------------

The ``reduce`` filter lets you group, sort, and limit the number of
resources to act on.  Maybe you want to delete AMIs, but want to do it in
small batches where you act on the oldest AMIs first.  Or maybe you want
to do some chaos engineering and randomly select ec2 instances part of
ASGs, but want to make sure no more than one instance per ASG is affected.
This filter lets you do that.

This works using this process:

    1. Group resources
    2. Sort each group of resources
    3. Selecting a number of resources in each group
    4. Combine the resulting resources

Grouping resources
~~~~~~~~~~~~~~~~~~

Resources are grouped based on the value extracted as defined by the
``group-by`` attribute.  All resources not able to extract a value are
placed in a group by themselves.  This is also the case when ``group-by``
is not specified.

Sorting resources
~~~~~~~~~~~~~~~~~

Sorting of individual resources within a group is controlled by a
combination of the ``sort-by`` and ``order`` attributes.  ``sort-by``
determines which value to use to sort and ``order`` controls how they are
sorted.  For any resources with a null value, those are by default sorted
last.  You can optionally sort those first with the ``null-order``
attribute.

Note: if neither ``sort-by`` or ``order`` are specified, no sorting is
done.

Selecting resources
~~~~~~~~~~~~~~~~~~~

Once groups have been sorted, we can then apply rules to select a specific
number of resources in each group.  We first ``discard`` some resources
and then ``limit`` the remaining set to a maximum count.

When the ``discard`` or ``discard-percent`` attributes are specified, we
take the ordered resources in each group and discard the first
``discard-percent`` of them or ``discard`` absolute count, whichever is
larger.

After discarding resources, we then limit the remaining set.
``limit-percent`` is applied first to reduce the number of resources to
this percentage of the original.  ``limit`` is then applied to allow for
an absolute count.  Resources are kept from the beginning of the list.

To explain this with an example, suppose you have 50 resources in a group
with all of these set:

  .. code-block:: yaml

    discard: 5
    discard-percent: 20
    limit: 10
    limit-percent: 30

This would first discard the first 10 resources because 20 percent of 50
is 10, which is greater than 5.  You now have 40 resources left in the
group and the limit settings are applied.  30% of 40 is 12, but ``limit``
is set to 10, which is lower, so the first 10 of the remaining are kept.
If they were numbered #1-50, you'd have discarded 1-10, kept 11-20, and
dropped the remaining 21-50.

If you had the following settings:

  .. code-block:: yaml

    discard-percent: 25
    limit-percent: 50

We'd discard the first 25% of 50 (12), then of the remaining 38 resources,
we'd keep 50% of those (19).  You'd end up with resources 13-31.

Now, some of these could eliminate all resources from a group.  If you
have 20 resources in one group and 5 in another and specify
``limit-percent = 10``, you'll get 2 resources from the first group and 0
resources from the second.

Combining resource groups
~~~~~~~~~~~~~~~~~~~~~~~~~

Once the groups have been modified, we now need to combine them back to
one set of resources.  Since the groups are determined by a JMESPath
expression, we sort the groups first based on the ``order`` attribute the
same way we sort within a group.  After the groups are sorted, it's a
simple concatenation of resources.

Attributes
~~~~~~~~~~

- ``group-by``, ``sort-by``

  These are both defined the same way...

  Note: For simplicity, you can specify these as just a single string
  which is treated as the ``key``.

  - ``key`` - The JMESPath expression to extract a value
  - ``value_regex`` - A regular expression with a single capture group that
    extracts a portion of the result of the ``key`` expression.
  - ``value_type`` - parse the value as one of the following:

    - ``string`` (default)
    - ``number``
    - ``date``

- ``order`` controls how to sorting is done

  - ``asc`` (default) - sort in ascending order based on ``key``
  - ``desc`` - sort in descending order based on ``key``
  - ``reverse`` - reverse the order of resources (ignores ``key``)
  - ``randomize`` - randomize the order of resources (ignores ``key``)

- ``null-order`` - when sorting, where to put resources that have a null value

  - ``last`` (default) - at the end of the list
  - ``first`` - at the start of the list

- ``discard`` - discard the first N resources within each group
- ``discard-percent`` - discard the first N percentage of resources within each group
- ``limit`` - select the first N resources within each group (after
  discards)
- ``limit-percent`` - select the first N percentage of resources within each group
  (after discards)

Examples
~~~~~~~~

This example will select the longest running instance from each ASG, then
randomly choose 10% of those, making sure to not affect more than 15
instances total, then terminate them.

  .. code-block:: yaml

   policies:
    - name: chaos-engineering
      resource: aws.ec2
      filters:
        - "State.Name": "running"
        - "tag:aws:autoscaling:groupName": present
        - type: reduce
          group-by: "tag:aws:autoscaling:groupName"
          sort-by: "LaunchTime"
          order: asc
          limit: 1
        - type: reduce
          order: randomize
          limit: 15
          limit-percent: 10
      actions:
        - terminate

This example will delete old AMIs, but make sure to only do the top 10
based on age.

  .. code-block:: yaml

    - name: limited-ami-expiration
      resource: aws.ami
      filters:
        - type: image-age
          days: 180
          op: ge
        - type: reduce
          sort-by: "CreationDate"
          order: asc
          limit: 10
      actions:
        - deregister

This example simply sorts the resources by when they are marked for
expiration.  We use a ``date`` type because the tags might be in
different date formats or are not text-sortable.

  .. code-block:: yaml

    - name: ami-expiration-by-expire-date
      resource: aws.ami
      filters:
        - type: value
          key: "tag:expire-after"
          value_type: age
          op: gt
          value: 0
        - type: reduce
          sort-by:
            key: "tag:expire-after"
            value_type: date
          order: asc
          limit: 10
      actions:
        - deregister
