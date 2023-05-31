# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import time
from abc import ABC
import abc

from c7n.utils import type_schema
from c7n.actions import BaseAction
from c7n_oci.actions.utils import all_operation_completed

log = logging.getLogger('custodian.oci.actions.base')

class OCIBaseAction(BaseAction, ABC):

    # OCIBaseAction handles the basic implementation of the OCI operation features
    #
    # Each action implementation can extends this class to get the basic OCI operation implementation
    # like fail_on_error, block_until_completion, etc
    #
    # fail_on_error : If any of the resource action execution is failed and if the fail_on_error is set to true, then
    # the execution of the policy will stop immediately with the error. If the fail_on_error is set to 'false', then
    # the policy execution will continue with the other resources by skipping the failed resource action. The resources.json
    # in the output directory will have the information about the lists of succeeded and failed resources.
    #
    # :example:
    #
    # Action that has the 'fail_on_error' set to false
    #
    # .. code-block:: yaml
    #
    #      policies:
    #         - name: tag-vm-policy
    #         description: |
    #             Adds a tag to a virtual machines
    #         resource: oci.compute
    #         filters:
    #             - type: query
    #               params:
    #                  compartment_id: 'ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value'
    #         actions:
    #             - type: update_instance
    #               params:
    #                  freeform-tags:
    #                     "Environment": "Test"
    #               fail_on_error: False
    #
    # batch_processing :  If the OCI resource operation invoked by the Policy action execution is Asynchronous in nature,
    # then setting the 'batch_processing' with true will run the jobs sequentially and waits until the submitted operation
    # reaches it's final state.
    #
    # :example:
    #
    # Action with the batch_processing on
    #
    # .. code-block:: yaml
    #
    #      policies:
    #         - name: scan-for-eligible-VMS
    #         description: Scan for all the VM's with standard shape
    #         resource: oci.compute
    #         filters:
    #            - type: query
    #              params:
    #                 compartment_id: 'ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value'
    #            - type: value
    #              key: shape
    #              value: VM.Standard2.4
    #         actions:
    #            - type: update_instance
    #            params:
    #               update_instance_details:
    #                  shape: VM.Standard.E3.Flex
    #                  shape_config:
    #                      ocpus: 1
    #            block_until_completion: True  # Run the action and wait untill the submitted operation gets completed

    # List that maintains the failed resources
    failed_resources = []
    fail_on_error = False
    batch_processing_enabled = False
    result = {'succeeded_resources': [],
              'failed_resources': failed_resources}
    work_request_client = None

    schema = {'properties': {
        'fail_on_error': {'type': 'boolean'},
        'block_until_completion': {'type': 'boolean'}
    }}

    def validate(self):
        if self.data.get('fail_on_error'):
            self.fail_on_error = self.data.get('fail_on_error')

    def handle_exception(self, resource, resources, exception):
        if self.fail_on_error:
            raise exception
        else:
            self.failed_resources.append(resource)
            resources.remove(resource)

    def process_result(self, resources):
        self.result.get('succeeded_resources').extend(resources)
        return self.result

    def process(self, resources):
        batch_processing = self.data.get('block_until_completion')
        if batch_processing:
            self.batch_processing_enabled = True
        if self.batch_processing_enabled:
            ## TODO: As of now setting the count value to '1'
            # count = batch_processing.get('count', 1)
            count = 1
            self.work_request_client = self.manager.get_session().get_work_request_client()
        resource_count = 0
        responses = []
        total_count = 0
        for resource in resources:
            try:
                response = self.perform_action(resource)
                if self.batch_processing_enabled:
                    responses.append(response)
                    resource_count = resource_count + 1
                    operations_completed = False
                    total_count = total_count + 1
                    if resource_count == count or total_count == len(resources):
                        while not operations_completed:
                            operations_completed = all_operation_completed(self.work_request_client, responses)
                            if not operations_completed:
                                log.info("Operations that are executed in batch are not completed. So waiting for 5 "
                                         "seconds...")
                                time.sleep(5)
                        resource_count = 0
                        responses.clear()
            except Exception as ex:
                log.exception(f"Unable to submit action against the instance - {resource['identifier']}. Reason: {ex.message}")
                self.handle_exception(resource, resources, ex)
        return self.process_result(resources)


    # All the OCI actions that extends the OCIBaseAction should implement the below method to have the logic
    # for invoking the respective client
    @abc.abstractmethod
    def perform_action(self, resource):
        raise NotImplementedError(
            "Base action class does not implement this behavior")

    def update_params(self, resource, updated_resource_details):
        updated_params = {}
        for key, value in updated_resource_details.items():
            if key == 'defined_tags':
                # Get all existing resource tags
                existing_tags = resource.get(key)
                # Create new dict to keep track of the tags provided in the policy
                updated_ns_tags = {}
                for tag_ns, tag_dict in value.items():
                    existing_ns_tags = existing_tags.get(tag_ns, {})
                    updated_tags = {k: v for k, v in tag_dict.items() if existing_ns_tags.get(k) == v}
                    updated_ns_tags[tag_ns] = updated_tags or tag_dict

                # Merge all the resource tags along with the policy provided ns tags
                merged_tags = {**existing_tags, **updated_ns_tags}
                value = merged_tags
            elif key == 'freeform_tags':
                existing_freeform_tags = resource.get(key, {})
                updated_freeform_tags = {k: v for k, v in value.items() if existing_freeform_tags.get(k) != v}
                value = {**existing_freeform_tags, **(updated_freeform_tags or value)}
            updated_params[key] = value
        return updated_params

class RemoveTagBaseAction(OCIBaseAction):
    schema = type_schema('remove_tag',
                         freeform_tags= {'type': 'array', 'items': {'type': 'string'}},
                         defined_tags= {'type': 'array', 'items': {'type': 'string'}},
                         rinherit=OCIBaseAction.schema)

    def remove_tag(self, resource):
        params_model = {}
        current_freeform_tags = resource.get('freeform_tags')
        current_defined_tags = resource.get('defined_tags')
        if self.data.get('freeform_tags'):
            delete_tag_lists = self.data.get('freeform_tags')
            for tag in delete_tag_lists:
                if tag in current_freeform_tags:
                    current_freeform_tags.pop(tag)
                else:
                    log.info('%s tag does not exists.', tag)
        if self.data.get('defined_tags'):
            delete_tag_lists = self.data.get('defined_tags')
            for tag in delete_tag_lists:
                splits = tag.split('.')
                if len(splits) == 2 and (splits[0] in current_defined_tags):
                    namespace = current_defined_tags.get(splits[0])
                    if splits[1] in namespace:
                        namespace.pop(splits[1])
                    else:
                        log.info('%s tag does not exists', splits[1])
                else:
                    log.info('Defined %s namespace might be wrong or does not exists in the resource - %s'
                             , splits[0], resource.get('display_name'))
        params_model['freeform_tags'] = current_freeform_tags
        params_model['defined_tags'] = current_defined_tags
        return params_model

    def tag_count(self, resource):
        freeform_tags = resource.get('freeform_tags')
        defined_tags = resource.get('defined_tags')
        tag_count = {}
        tag_count['freeform_tags'] = len(freeform_tags)

        for namespace in defined_tags:
            namespace_tag_count = {}
            namespace_tag_count[namespace] = len(defined_tags.get(namespace))
            tag_count['defined_tags'] = namespace_tag_count
        return tag_count

    def tag_removed_from_resource(self, original_tag_count, modified_tag_count):
        if original_tag_count.get('freeform_tags') != modified_tag_count.get('freeform_tags'):
            return True
        else:
            original_defined_tag = original_tag_count.get('defined_tags')
            modified_defined_tag = modified_tag_count.get('defined_tags')
            if original_defined_tag:
                for namespace in original_defined_tag:
                    if original_defined_tag.get(namespace) != modified_defined_tag.get(namespace):
                        return True
                return False
            else:
                return False



