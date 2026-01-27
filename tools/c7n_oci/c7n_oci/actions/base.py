# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import abc
import copy
import logging
from abc import ABC

from c7n.actions import BaseAction
from c7n.utils import type_schema

log = logging.getLogger("custodian.oci.actions.base")


class OCIBaseAction(BaseAction, ABC):
    failed_resources = []
    batch_processing_enabled = False
    result = {"succeeded_resources": [], "failed_resources": failed_resources}
    work_request_client = None
    fail_on_error = True

    schema = {
        "properties": {
            "fail_on_error": {"type": "boolean"},
            "block_until_completion": {"type": "boolean"},
        }
    }

    def handle_exception(self, resource, resources, exception):
        if self.fail_on_error:
            raise exception
        else:
            self.failed_resources.append(resource)
            resources.remove(resource)

    def process_result(self, resources):
        self.result.get("succeeded_resources").extend(resources)
        return self.result

    def process(self, resources):
        batch_processing = self.data.get("block_until_completion")
        if batch_processing:
            self.batch_processing_enabled = False
        for resource in resources:
            try:
                self.perform_action(resource)
            except Exception as ex:
                res = resource.get("id", resource.get("name"))
                log.exception(
                    f"Unable to submit action against the instance - {res} Reason: {{ex.message}}"
                )
                self.handle_exception(resource, resources, ex)
        return self.process_result(resources)

    # All the OCI actions that extends the OCIBaseAction should implement the below method to
    # have the logic for invoking the respective client
    @abc.abstractmethod
    def perform_action(self, resource):
        raise NotImplementedError("Base action class does not implement this behavior")

    def extract_params(self, params):
        op_params = copy.deepcopy(params)
        del op_params["type"]
        return op_params

    def update_params(self, resource, updated_resource_details):
        updated_params = {}
        for key, value in updated_resource_details.items():
            if key == "defined_tags":
                # Get all existing resource tags
                existing_tags = resource.get(key)
                # Create new dict to keep track of the tags provided in the policy
                updated_ns_tags = {}
                for tag_ns, tag_dict in value.items():
                    existing_ns_tags = existing_tags.get(tag_ns, {})
                    updated_tags = {
                        k: v for k, v in tag_dict.items() if existing_ns_tags.get(k) == v
                    }
                    updated_ns_tags[tag_ns] = updated_tags or tag_dict

                # Merge all the resource tags along with the policy provided ns tags
                merged_tags = {**existing_tags, **updated_ns_tags}
                value = merged_tags
            elif key == "freeform_tags":
                existing_freeform_tags = resource.get(key, {})
                updated_freeform_tags = {
                    k: v for k, v in value.items() if existing_freeform_tags.get(k) != v
                }
                value = {**existing_freeform_tags, **(updated_freeform_tags or value)}
            updated_params[key] = value
        return updated_params


class RemoveTagBaseAction(OCIBaseAction):
    schema = type_schema(
        "remove-tag",
        freeform_tags={"type": "array", "items": {"type": "string"}},
        defined_tags={"type": "array", "items": {"type": "string"}},
        rinherit=OCIBaseAction.schema,
    )

    def remove_tag(self, resource):
        params_model = {}
        current_freeform_tags = resource.get("freeform_tags")
        current_defined_tags = resource.get("defined_tags")
        if self.data.get("freeform_tags"):
            delete_tag_lists = self.data.get("freeform_tags")
            for tag in delete_tag_lists:
                if tag in current_freeform_tags:
                    current_freeform_tags.pop(tag)
                else:
                    log.info("%s tag does not exists.", tag)
        if self.data.get("defined_tags"):
            delete_tag_lists = self.data.get("defined_tags")
            for tag in delete_tag_lists:
                splits = tag.split(".")
                if len(splits) == 2 and (splits[0] in current_defined_tags):
                    namespace = current_defined_tags.get(splits[0])
                    if splits[1] in namespace:
                        namespace.pop(splits[1])
                    else:
                        log.info("%s tag does not exists", splits[1])
                else:
                    log.info(
                        (
                            "Defined %s namespace might be wrong or does not exists in the"
                            " resource - %s"
                        ),
                        splits[0],
                        resource.get("name"),
                    )
        params_model["freeform_tags"] = current_freeform_tags
        params_model["defined_tags"] = current_defined_tags
        return params_model

    def tag_count(self, resource):
        freeform_tags = resource.get("freeform_tags")
        defined_tags = resource.get("defined_tags")
        tag_count = {}
        tag_count["freeform_tags"] = len(freeform_tags)

        namespace_tag_count = {}
        for namespace in defined_tags:
            namespace_tag_count[namespace] = len(defined_tags.get(namespace))
        tag_count["defined_tags"] = namespace_tag_count
        return tag_count

    def tag_removed_from_resource(self, original_tag_count, modified_tag_count):
        if original_tag_count.get("freeform_tags") != modified_tag_count.get("freeform_tags"):
            return True
        else:
            original_defined_tag = original_tag_count.get("defined_tags")
            modified_defined_tag = modified_tag_count.get("defined_tags")
            if original_defined_tag:
                for namespace in original_defined_tag:
                    if original_defined_tag.get(namespace) != modified_defined_tag.get(namespace):
                        return True
                return False
            else:
                return False
