.. _oci_function:

Function Support
----------------------

`Oracle Cloud Infrastructure (OCI) Function <https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsoverview.htm>`_ is a fully managed, multi-tenant, highly scalable, on-demand, Functions-as-a-Service platform.
OCI Functions provides powerful realtime Oracle Cloud Infrastructure Events based code execution on the state changes of resources throughout your tenancy.

Oracle Cloud Infrastructure Events
++++++++++++++++++++++++++++++++++

`Oracle Cloud Infrastructure Events 
<https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm>`_ enables you to create automation based on the state changes of resources throughout your tenancy. 
Use Events to allow your development teams to automatically respond when a resource changes its state.
Review the Oracle Cloud Infrastructure services that emit `events. <https://docs.oracle.com/en-us/iaas/Content/Events/Reference/eventsproducers.htm>`_

Cloud Custodian Integration
+++++++++++++++++++++++++++

Custodian provides policy level execution against `Oracle Cloud Infrastructure Events <https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm>`_. Each
Custodian policy can be deployed as an independent OCI function. The only
difference between a Custodian policy that runs in OCI function and one that runs
directly from the CLI in poll mode is the specification of the subscription of
the events in the mode config block of the policy.

Internally Custodian will reconstitute current state for all the resources
in the event, execute the policy against them, match against the
policy filters, and apply the policy actions to matching resources.

Prerequisites
#############

1. Install and start Docker
   In a terminal window in your development environment:

  1. Confirm that Docker is installed by entering

    .. code-block:: console

      docker version

    If you see an error message indicating that Docker is not installed, you have to install Docker before proceeding. 
    See the `Docker documentation <https://docs.docker.com/>`_ for your platform

  2. Launch the standard hello-world Docker image as a container to confirm that Docker is running by entering

    .. code-block:: console

      docker run hello-world
    
    If you see an error message indicating that Docker is not running, 
    you have to start the Docker daemon before proceeding. See the `Docker documentation <https://docs.docker.com/>`_
  
2. Set OCI_AUTH_TOKEN environment variable.

  If you don't have Auth Token, then please follow the instruction mentioned in https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrygettingauthtoken.htm to generate the token.

  .. code-block:: console

    export OCI_AUTH_TOKEN=6aN___________6MqX

Example Policy
##############

.. code-block:: yaml

  policies:
  - name: auto-tag-bucket
    resource: oci.bucket
    mode:
      type: oci-event
      subnets: 
        - ocid1.subnet.oc1..<unique_ID>
      events: 
        - createbucket
    actions:
      - type: update
        freeform_tags:
          CreatedBy: CloudCustodian

Refer to :ref:`Oracle Cloud Infrastructure_modes` for detailed explanation of the different ``type``
values and the corresponding additional configuration options.

Resources created on policy execution
#####################################

1. Application and Function
2. Event rule
3. :ref:`oci-policy`
4. In the root compartment of the tenancy, a repository named cloudcustodian/c7n-oci has been created, and the Custodian Docker image has been pushed to this repository.

If a compartment ID is specified in the environment variable, the application, function, and event rule will be created within that specified compartment. Otherwise, they will be created in the root compartment. Dynamic Group, OCI policy, and the cloudcustodian/c7n-oci repository will always be created in the root compartment.

.. _oci-policy:

OCI Policy/Permissions
######################

To enable a function to access another Oracle Cloud Infrastructure resources - 
  1. It creates the dynamic group named custodian-fn-<compartment id> and associates the corresponding function with it.

    Example of dynamic group rule Condition -  Any{resource.id= <function_id>}

  2. A policy named custodian-function-policy is then created.

    Example policy - allow dynamic-group custodian-fn-<compartment id> to manage all-resources in compartment id <compartment id>




