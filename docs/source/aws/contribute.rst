.. _aws_contribute:

Developer Guide
=================

Cloud Custodian is a Python application and supports Python 3 on MacOS, Linux, and Windows. It is recommended 
using Python 3.7 or higher.

Run the following commands in the root directory after cloning Cloud Custodian:

.. code-block:: bash

    $ make install
    $ source bin/activate

This creates a virtual env in your enlistment and installs all packages as editable.

Now you may run ``custodian`` with any flags in order to directly test changes to the source files.  For example, 
``custodian schema aws.<resource_type>`` will return schema for resource type.


Adding New AWS Resources
==========================

Create New AWS Resource
-------------------------

Each class definition will use the ``@resources.register('<resource_name>')`` decorator to register that class as a Custodian resource 
substituting `<resource_name>` with the new resource name. The name specified in the decorator is how the resource will be referenced 
within policies.

Register the new resource: ``@resources.register(‘<resource_name>’)``

An outer class defining the reference in resource mapping: ``class <resource_type>(query.QueryResourceManager)``

Interior class that defines the aws metadata for resource
``class resource_type(query.TypeInfo)``:

.. code-block:: python

    """Resource Type Metadata"""

    ###########
    # Required

    # id field, should be the identifier used for apis
    id = None

    # name field, used for display
    name = None

    # which aws service (per sdk) has the api for this resource.
    service = None

    # used to query the resource by describe-sources
    enum_spec = None

    ###########
    # Optional

    ############
    # Permissions

    # Permission string prefix if not service
    permission_prefix = None

    # Permissions for resource enumeration/get. Normally we autogen
    # but in some cases we need to specify statically
    permissions_enum = None

    # Permissions for resourcee augment
    permissions_augment = None

    ###########
    # Arn handling / generation metadata

    # arn resource attribute, when describe format has arn
    arn = None

    # type, used for arn construction, also required for universal tag augment
    arn_type = None

    # how arn type is separated from rest of arn
    arn_separator = "/"

    # for services that need custom labeling for arns
    arn_service = None

    ##########
    # Resource retrieval

    # filter_name, when fetching a single resource via enum_spec
    # technically optional, but effectively required for serverless
    # event policies else we have to enumerate the population.
    filter_name = None

    # filter_type, scalar or list
    filter_type = None

    # used to enrich the resource descriptions returned by enum_spec
    detail_spec = None

    # used when the api supports getting resource details enmasse
    batch_detail_spec = None

    ##########
    # Misc

    # used for reporting, array of fields
    default_report_fields = ()

    # date, latest date associated to resource, generally references
    # either create date or modified date.
    date = None

    # dimension, defines that resource has cloud watch metrics and the
    # resource id can be passed as this value. further customizations
    # of dimensions require subclass metrics filter.
    dimension = None

    # AWS Cloudformation type
    cfn_type = None

    # AWS Config Service resource type name
    config_type = None

    # Whether or not resource group tagging api can be used, in which
    # case we'll automatically register tag actions/filters.
    #
    # Note values of True will register legacy tag filters/actions, values
    # of object() will just register current standard tag/filters/actions.
    universal_taggable = False

    # Denotes if this resource exists across all regions (iam, cloudfront, r53)
    global_resource = False

    # Generally we utilize a service to namespace mapping in the metrics filter
    # however some resources have a type specific namespace (ig. ebs)
    metrics_namespace = None

    # specific to ec2 service resources used to disambiguate a resource by its id
    id_prefix = None


An example that adds a new resource:


.. code-block:: python

    @resources.register('scaling-policies')
    class ScalingPolicies(query.QueryResourceManager):

        # interior class that defines the aws metadata for resource
        class resource_type(query.TypeInfo):
            service = 'autoscaling'
            arn_type = "scalingPolicy" 
            id = name = 'PolicyName'
            date = 'CreatedTime'

            # this defines the boto3 call for the resource as well as JMESPATH
            # for accessing TL resources
            enum_spec = (
                'describe_policies', 'ScalingPolicies', None
            )
            filter_name = 'PolicyNames'
            filter_type = 'list'
            cfn_type = config_type = 'AWS::AutoScaling::ScalingPolicy'


Load New AWS Resource
---------------------

If you created a new module for an AWS service (i.e. this was the first resource implemented for this service in Custodian),
then import the new service module in ``resource_map.py``:

.. code-block:: python

    "aws.<name of resource>": "c7n.resources.<name of file>.<name of resource class>"


Add New Filter
---------------

A filter can be added with a decorator and class:
 
``@<New-resource-class>.filter_registry.register('<filter-name>')``

``class <NewFilterName>(ValueFilter)``


An example that adds a new filter for scaling policies to the ASG resource:

.. code-block:: python

    @ASG.filter_registry.register('scaling-policies')
    class ScalingPoliciesFilter(ValueFilter):
        schema = type_schema(
            'scaling-policies', rinherit=ValueFilter.schema
        )
        schema_alias = False
        permissions = ("autoscaling:DescribePolicies",)

        def process(self, asgs, event=None):
            self.policy_info = PolicyInfo(self.manager).initialize(asgs)
            return super(ScalingPoliciesFilter, self).process(asgs, event)

        def __call__(self, asg):

            asg_policies = self.policy_info.get(asg)
            matched = False
            if asg_policies is not None:
                for policy in asg_policies:
                    matched = self.match(policy) or matched
            return matched



Add New Action
---------------

An action can be added with a decorator and class:

``@<New-resource-class>.action_registry.register('<action-name>')``

``class <NewActionName>(Action)``


An example that adds a new action for deleting to the ASG resource:

.. code-block:: python

    @ASG.action_registry.register('delete')
    class Delete(Action):

        schema = type_schema('delete', force={'type': 'boolean'})
        permissions = ("autoscaling:DeleteAutoScalingGroup",)

        def process(self, asgs):
            client = local_session(
                self.manager.session_factory).client('autoscaling')
            for asg in asgs:
                self.process_asg(client, asg)

        def process_asg(self, client, asg):
            force_delete = self.data.get('force', False)
            try:
                self.manager.retry(
                    client.delete_auto_scaling_group,
                    AutoScalingGroupName=asg['AutoScalingGroupName'],
                    ForceDelete=force_delete)
            except ClientError as e:
                if e.response['Error']['Code'] == 'ValidationError':
                    return
                raise


Testing
---------------------

For information regarding testing see :ref:`testing for developers<developer-tests>`.
