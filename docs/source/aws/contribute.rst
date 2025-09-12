.. _aws_contribute:

Developer Guide
=================

Cloud Custodian is a Python application and supports Python 3 on MacOS, Linux, and Windows. It is recommended 
using Python 3.7 or higher.

Run the following commands in the root directory after cloning Cloud Custodian:

.. code-block:: bash

    make install
    source bin/activate

This creates a virtual env in your enlistment and installs all packages as editable.

Now you may run ``custodian`` with any flags in order to directly test changes to the source files.  For example, 
``custodian schema aws.<resource_type>`` will return schema for resource type.


Adding New AWS Resources
==========================

3rd Party Documentation
------------------------

`John Lonergan's guide to adding an extension.<https://gist.github.com/Johnlon/98e1e4b9aaedfedead428c89e7dab5bb>`


Create New AWS Resource
-------------------------

Each class definition will use the ``@resources.register('<resource_name>')`` decorator to register that class as a Custodian resource 
substituting `<resource_name>` with the new resource name. The name specified in the decorator is how the resource will be referenced within policies.

Register the new resource: ``@resources.register(‘<resource_name>’)``

An outer class defining the reference in resource mapping: ``class <resource_type>(query.QueryResourceManager)``

Interior class that defines the aws metadata for resource
``class resource_type(query.TypeInfo)``:

.. autoclass:: c7n.query.TypeInfo

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
