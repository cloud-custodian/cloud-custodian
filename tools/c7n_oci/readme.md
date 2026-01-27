# Cloud Custodian - OCI Support

This is a plugin to Cloud Custodian that adds OCI support.

## Install Cloud Custodian and OCI Plugin

The OCI provider must be installed as a separate package in addition to c7n.

    $ git clone https://github.com/cloud-custodian/cloud-custodian.git
    $ virtualenv custodian
    $ source custodian/bin/activate
    (custodian) $ pip install -e cloud-custodian/.
    (custodian) $ pip install -e cloud-custodian/tools/c7n_oci/.

## Write your first policy

Cloud Custodian policies are expressed in YAML and include the following:

* The type of resource to run the policy against
* Filters to narrow down the set of resources
* Actions to take on the filtered set of resources

Our first policy filters compute instance of a specific name, then adds the tag ``mark_deletion: true``.

Create a file named ``custodian.yml`` with the following content. Update ``display_name``,``compartment_id`` match an existing compute instance.

    policies:
        - name: filter-for-compute-name
          description: Filter for compute which matches the display name
          resource: oci.instance
          filters:
            - type: query
              params:
                compartment_id: 'ocid1.compartment.oc1..<unique_ID>'
            - type: value
              key: display_name
              value: test
          actions:
            - type: update_instance
              params:
                update_instance_details:
                    freeform_tags:
                        mark-for-deletion: 'true'

## Run your policy

    custodian run --output-dir=. custodian.yml

If successful, you should see output like the following on the command line::

    2023-05-25 18:15:53,132: custodian.oci.session:INFO Successfully authenticated user ...
    2023-05-25 18:16:01,118: custodian.policy:INFO policy:filter-for-compute-name resource:oci.instance region: count:1 time:7.98
    2023-05-25 18:16:05,474: custodian.oci.resources.compute:INFO Received status 200 for PUT:update_instance 9A14E2D68AC94772849C7534E10BC963/089249DEBA83A0BDA6050BFF759BCF49/38040CF37F356743B539E653B2DED1E0
    2023-05-25 18:16:05,483: custodian.policy:INFO policy:filter-for-compute-name action:updateinstance resources:1 execution_time:4.34

You can find a new ``filter-for-compute-name`` under --output-dir option value directory with a log and a ``resources.json`` file.

## Links
- [Getting Started](https://cloudcustodian.io/docs/oci/gettingstarted.html)
- [Example Scenarios](https://cloudcustodian.io/docs/oci/examples/index.html)