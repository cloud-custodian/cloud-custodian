# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import re  # noqa
import copy  # noqa

import oci.identity

from c7n.filters import Filter, ValueFilter  # noqa
from c7n.utils import type_schema
from c7n_oci.actions.base import OCIBaseAction, RemoveTagBaseAction
from c7n_oci.provider import resources
from c7n_oci.query import QueryResourceManager

log = logging.getLogger("custodian.oci.resources.identity")


@resources.register("compartment")
class Compartment(QueryResourceManager):
    """Oracle Cloud Infrastructure Compartment Resource

    :example:

    Returns all Compartment resources in the tenancy

    .. code-block:: yaml

        policies:
            - name: find-all-compartment-resources
              resource: oci.compartment

    """

    class resource_type:
        doc_groups = ["Identity"]
        service = "oci.identity"
        client = "IdentityClient"
        enum_spec = ("list_compartments", "items[]", None)
        extra_params = {"compartment_id"}
        resource_type = "OCI.Identity/Compartment"
        id = "id"
        name = "name"
        search_resource_type = "compartment"


@Compartment.action_registry.register("update")
class UpdateCompartmentAction(OCIBaseAction):
    """
    Update compartment Action

    :example:

    Updates the specified compartment's description or name. You can't update the root compartment.

    Please refer to the Oracle Cloud Infrastructure Python SDK documentation for parameter details to this action
    https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/client/oci.identity.IdentityClient.html#oci.identity.IdentityClient.update_compartment

    .. code-block:: yaml

        policies:
            - name: perform-update-compartment-action
              resource: oci.compartment
              actions:
                - type: update
                  defined_tags:
                     Cloud_Custodian: True
                  freeform_tags:
                     Environment: development

    """  # noqa

    schema = type_schema(
        "update", **{"freeform_tags": {"type": "object"}, "defined_tags": {"type": "object"}}
    )

    def perform_action(self, resource):
        client = self.manager.get_client()
        update_compartment_details_user = self.extract_params(self.data)
        params_model = self.update_params(resource, update_compartment_details_user)
        update_compartment_details = oci.identity.models.UpdateCompartmentDetails(**params_model)
        response = client.update_compartment(
            compartment_id=resource.get("id"), update_compartment_details=update_compartment_details
        )
        log.info(
            f"Received status {response.status} for PUT:update_compartment {response.request_id}"
        )
        return response


@Compartment.action_registry.register("remove-tag")
class RemoveTagActionCompartment(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as 'namespace.tagName' as below in the policy file.

    .. code-block:: yaml

        policies:
            - name: remove-tag
              resource: oci.compartment
            actions:
              - type: remove-tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """  # noqa

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_dict["compartment_id"] = resource.get("id")
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict["update_compartment_details"] = oci.identity.models.UpdateCompartmentDetails(
            **params_model
        )
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_compartment(
                compartment_id=params_dict["compartment_id"],
                update_compartment_details=params_dict["update_compartment_details"],
            )
            log.debug(
                f"Received status {response.status} for PUT:update_compartment:remove-tag"
                f" {response.request_id}"
            )
            return response
        else:
            log.debug(
                "No tags matched. Skipping the remove-tag action on this resource - %s",
                resource.get("name"),
            )
            return None


@resources.register("group")
class Group(QueryResourceManager):
    """Oracle Cloud Infrastructure Group Resource

    :example:

    Returns all Group resources in the tenancy

    .. code-block:: yaml

        policies:
            - name: find-all-group-resources
              resource: oci.group

    """

    class resource_type:
        doc_groups = ["Identity"]
        service = "oci.identity"
        client = "IdentityClient"
        enum_spec = ("list_groups", "items[]", None)
        extra_params = {"compartment_id"}
        resource_type = "OCI.Identity/Group"
        id = "id"
        name = "name"
        search_resource_type = "group"


@Group.action_registry.register("update")
class UpdateGroupAction(OCIBaseAction):
    """
    Update group Action

    :example:

    Updates the specified group.

    Please refer to the Oracle Cloud Infrastructure Python SDK documentation for parameter details to this action
    https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/client/oci.identity.IdentityClient.html#oci.identity.IdentityClient.update_group

    .. code-block:: yaml

        policies:
            - name: perform-update-group-action
              resource: oci.group
              actions:
                - type: update
                  defined_tags:
                     Cloud_Custodian: True
                  freeform_tags:
                     Environment: development

    """  # noqa

    schema = type_schema(
        "update", **{"freeform_tags": {"type": "object"}, "defined_tags": {"type": "object"}}
    )

    def perform_action(self, resource):
        client = self.manager.get_client()
        update_group_details_user = self.extract_params(self.data)
        params_model = self.update_params(resource, update_group_details_user)
        update_group_details = oci.identity.models.UpdateGroupDetails(**params_model)
        response = client.update_group(
            group_id=resource.get("id"), update_group_details=update_group_details
        )
        log.info(f"Received status {response.status} for PUT:update_group {response.request_id}")
        return response


@Group.action_registry.register("remove-tag")
class RemoveTagActionGroup(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as 'namespace.tagName' as below in the policy file.

    .. code-block:: yaml

        policies:
            - name: remove-tag
              resource: oci.group
            actions:
              - type: remove-tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """  # noqa

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_dict["group_id"] = resource.get("id")
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict["update_group_details"] = oci.identity.models.UpdateGroupDetails(**params_model)
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_group(
                group_id=params_dict["group_id"],
                update_group_details=params_dict["update_group_details"],
            )
            log.debug(
                f"Received status {response.status} for PUT:update_group:remove-tag"
                f" {response.request_id}"
            )
            return response
        else:
            log.debug(
                "No tags matched. Skipping the remove-tag action on this resource - %s",
                resource.get("name"),
            )
            return None


@resources.register("user")
class User(QueryResourceManager):
    """Oracle Cloud Infrastructure User Resource

    :example:

    Returns all User resources in the tenancy

    .. code-block:: yaml

        policies:
            - name: find-all-user-resources
              resource: oci.user

    """

    class resource_type:
        doc_groups = ["Identity"]
        service = "oci.identity"
        client = "IdentityClient"
        enum_spec = ("list_users", "items[]", None)
        extra_params = {"compartment_id"}
        resource_type = "OCI.Identity/User"
        id = "id"
        name = "name"
        search_resource_type = "user"


@User.action_registry.register("update")
class UpdateUserAction(OCIBaseAction):
    """
    Update user Action

    :example:

    Updates the description of the specified user.

    Please refer to the Oracle Cloud Infrastructure Python SDK documentation for parameter details to this action
    https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/client/oci.identity.IdentityClient.html#oci.identity.IdentityClient.update_user

    .. code-block:: yaml

        policies:
            - name: perform-update-user-action
              resource: oci.user
              actions:
                - type: update
                  defined_tags:
                     Cloud_Custodian: True
                  freeform_tags:
                     Environment: development


    """  # noqa

    schema = type_schema(
        "update", **{"freeform_tags": {"type": "object"}, "defined_tags": {"type": "object"}}
    )

    def perform_action(self, resource):
        client = self.manager.get_client()
        update_user_details_user = self.extract_params(self.data)
        params_model = self.update_params(resource, update_user_details_user)
        update_user_details = oci.identity.models.UpdateUserDetails(**params_model)
        response = client.update_user(
            user_id=resource.get("id"), update_user_details=update_user_details
        )
        log.info(f"Received status {response.status} for PUT:update_user {response.request_id}")
        return response


@User.action_registry.register("remove-tag")
class RemoveTagActionUser(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as 'namespace.tagName' as below in the policy file.

    .. code-block:: yaml

        policies:
            - name: remove-tag
              resource: oci.user
            actions:
              - type: remove-tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """  # noqa

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_dict["user_id"] = resource.get("id")
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict["update_user_details"] = oci.identity.models.UpdateUserDetails(**params_model)
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_user(
                user_id=params_dict["user_id"],
                update_user_details=params_dict["update_user_details"],
            )
            log.debug(
                f"Received status {response.status} for PUT:update_user:remove-tag"
                f" {response.request_id}"
            )
            return response
        else:
            log.debug(
                "No tags matched. Skipping the remove-tag action on this resource - %s",
                resource.get("name"),
            )
            return None


@User.filter_registry.register("attributes")
class AttributesValueFilter(ValueFilter):
    """
    Get all the attributes attached to this resources

    :example:

        Get all the attributes associated with this User resource

    .. code-block:: yaml

        policies:
            - name: get-user-attributes
              resource: oci.user
              filters:
                - type: attributes
                  key: attr1
                  value: value1
    """

    schema = type_schema("attributes", rinherit=ValueFilter.schema)

    def process(self, resources, event):
        result = []
        for resource in resources:
            response = self.manager.get_client().get_user(
                user_id=resource.get("id"),
            )
            user = oci.util.to_dict(response.data)
            resource = {**resource, **user}
            result.append(resource)
        return super().process(result)


@User.filter_registry.register("o-auth2-client-credentials")
class UserOAuth2ClientCredentialsValueFilter(ValueFilter):
    """
    Filters user resources by o_auth2_client_credential.

    :example:

    This policy will find all user whose o_auth2_client_credential is 'INACTIVE'

    .. code-block:: yaml

        policies:
            - name: filter-user-with-inactive-o_auth2_client_credentials
              resource: oci.user
              filters:
                - type: o-auth2-client-credentials
                  key: o_auth2_client_credential.lifecycle_state
                  value: 'INACTIVE'
                  op: equal

    """

    schema = type_schema("o-auth2-client-credentials", rinherit=ValueFilter.schema)

    def process(self, resources, event):
        if "value_type" in self.data and self.data["value_type"] == "size":
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                if "o_auth2_client_credentials" in resource:
                    result.append(resource)
                else:
                    response = self.manager.get_client().list_o_auth_client_credentials(
                        user_id=params_dict["user_id"],
                    )
                    o_auth2_client_credentials = response.data
                    if o_auth2_client_credentials:
                        res["o_auth2_client_credentials"] = oci.util.to_dict(
                            o_auth2_client_credentials
                        )
                        result.append(res)
            return super().process(result)
        else:
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                response = self.manager.get_client().list_o_auth_client_credentials(
                    user_id=params_dict["user_id"],
                )
                o_auth2_client_credentials = response.data
                if o_auth2_client_credentials:
                    for o_auth2_client_credential in o_auth2_client_credentials:
                        res["o_auth2_client_credential"] = oci.util.to_dict(
                            o_auth2_client_credential
                        )
                        result.append(res)
            filtered_resources = super().process(result)
            deserialized_resources = []
            for filtered_resource in filtered_resources:
                id = filtered_resource["id"]
                key = filtered_resource["o_auth2_client_credential"]
                key_added = False
                for res in deserialized_resources:
                    if res["id"] == id:
                        res["o_auth2_client_credentials"].append(key)
                        key_added = True
                        break
                if not key_added:
                    filtered_user = copy.deepcopy(filtered_resource)
                    if "o_auth2_client_credentials" in filtered_user:
                        filtered_user["o_auth2_client_credentials"].clear()
                        filtered_user["o_auth2_client_credentials"].append(key)
                    else:
                        filtered_user["o_auth2_client_credentials"] = []
                        filtered_user["o_auth2_client_credentials"].append(key)
                    if "o_auth2_client_credential" in filtered_user:
                        filtered_user.pop("o_auth2_client_credential")
                    deserialized_resources.append(filtered_user)
            return deserialized_resources


@User.filter_registry.register("smtp-credentials")
class UserSmtpCredentialsValueFilter(ValueFilter):
    """
    Filters user resources by smtp_credential.

    :example:

    This policy will find all user whose smtp_credential is 'INACTIVE'

    .. code-block:: yaml

        policies:
            - name: filter-user-with-inactive-smtp_credentials
              resource: oci.user
              filters:
                - type: smtp-credentials
                  key: smtp_credential.lifecycle_state
                  value: 'INACTIVE'
                  op: equal

    """

    schema = type_schema("smtp-credentials", rinherit=ValueFilter.schema)

    def process(self, resources, event):
        if "value_type" in self.data and self.data["value_type"] == "size":
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                if "smtp_credentials" in resource:
                    result.append(resource)
                else:
                    response = self.manager.get_client().list_smtp_credentials(
                        user_id=params_dict["user_id"],
                    )
                    smtp_credentials = response.data
                    if smtp_credentials:
                        res["smtp_credentials"] = oci.util.to_dict(smtp_credentials)
                        result.append(res)
            return super().process(result)
        else:
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                response = self.manager.get_client().list_smtp_credentials(
                    user_id=params_dict["user_id"],
                )
                smtp_credentials = response.data
                if smtp_credentials:
                    for smtp_credential in smtp_credentials:
                        res["smtp_credential"] = oci.util.to_dict(smtp_credential)
                        result.append(res)
            filtered_resources = super().process(result)
            deserialized_resources = []
            for filtered_resource in filtered_resources:
                id = filtered_resource["id"]
                key = filtered_resource["smtp_credential"]
                key_added = False
                for res in deserialized_resources:
                    if res["id"] == id:
                        res["smtp_credentials"].append(key)
                        key_added = True
                        break
                if not key_added:
                    filtered_user = copy.deepcopy(filtered_resource)
                    if "smtp_credentials" in filtered_user:
                        filtered_user["smtp_credentials"].clear()
                        filtered_user["smtp_credentials"].append(key)
                    else:
                        filtered_user["smtp_credentials"] = []
                        filtered_user["smtp_credentials"].append(key)
                    if "smtp_credential" in filtered_user:
                        filtered_user.pop("smtp_credential")
                    deserialized_resources.append(filtered_user)
            return deserialized_resources


@User.filter_registry.register("customer-secret-keys")
class UserCustomerSecretKeysValueFilter(ValueFilter):
    """
    Filters user resources by customer_secret_key.

    :example:

    This policy will find all user whose customer_secret_key is 'INACTIVE'

    .. code-block:: yaml

        policies:
            - name: filter-user-with-inactive-customer_secret_keys
              resource: oci.user
              filters:
                - type: customer-secret-keys
                  key: customer_secret_key.lifecycle_state
                  value: 'INACTIVE'
                  op: equal

    """

    schema = type_schema("customer-secret-keys", rinherit=ValueFilter.schema)

    def process(self, resources, event):
        if "value_type" in self.data and self.data["value_type"] == "size":
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                if "customer_secret_keys" in resource:
                    result.append(resource)
                else:
                    response = self.manager.get_client().list_customer_secret_keys(
                        user_id=params_dict["user_id"],
                    )
                    customer_secret_keys = response.data
                    if customer_secret_keys:
                        res["customer_secret_keys"] = oci.util.to_dict(customer_secret_keys)
                        result.append(res)
            return super().process(result)
        else:
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                response = self.manager.get_client().list_customer_secret_keys(
                    user_id=params_dict["user_id"],
                )
                customer_secret_keys = response.data
                if customer_secret_keys:
                    for customer_secret_key in customer_secret_keys:
                        res["customer_secret_key"] = oci.util.to_dict(customer_secret_key)
                        result.append(res)
            filtered_resources = super().process(result)
            deserialized_resources = []
            for filtered_resource in filtered_resources:
                id = filtered_resource["id"]
                key = filtered_resource["customer_secret_key"]
                key_added = False
                for res in deserialized_resources:
                    if res["id"] == id:
                        res["customer_secret_keys"].append(key)
                        key_added = True
                        break
                if not key_added:
                    filtered_user = copy.deepcopy(filtered_resource)
                    if "customer_secret_keys" in filtered_user:
                        filtered_user["customer_secret_keys"].clear()
                        filtered_user["customer_secret_keys"].append(key)
                    else:
                        filtered_user["customer_secret_keys"] = []
                        filtered_user["customer_secret_keys"].append(key)
                    if "customer_secret_key" in filtered_user:
                        filtered_user.pop("customer_secret_key")
                    deserialized_resources.append(filtered_user)
            return deserialized_resources


@User.filter_registry.register("db-credentials")
class UserDbCredentialsValueFilter(ValueFilter):
    """
    Filters user resources by db_credential.

    :example:

    This policy will find all user whose db_credential is 'INACTIVE'

    .. code-block:: yaml

        policies:
            - name: filter-user-with-inactive-db_credentials
              resource: oci.user
              filters:
                - type: db-credentials
                  key: db_credential.lifecycle_state
                  value: 'INACTIVE'
                  op: equal

    """

    schema = type_schema("db-credentials", rinherit=ValueFilter.schema)

    def process(self, resources, event):
        if "value_type" in self.data and self.data["value_type"] == "size":
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                if "db_credentials" in resource:
                    result.append(resource)
                else:
                    response = self.manager.get_client().list_db_credentials(
                        user_id=params_dict["user_id"],
                    )
                    db_credentials = response.data
                    if db_credentials:
                        res["db_credentials"] = oci.util.to_dict(db_credentials)
                        result.append(res)
            return super().process(result)
        else:
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                response = self.manager.get_client().list_db_credentials(
                    user_id=params_dict["user_id"],
                )
                db_credentials = response.data
                if db_credentials:
                    for db_credential in db_credentials:
                        res["db_credential"] = oci.util.to_dict(db_credential)
                        result.append(res)
            filtered_resources = super().process(result)
            deserialized_resources = []
            for filtered_resource in filtered_resources:
                id = filtered_resource["id"]
                key = filtered_resource["db_credential"]
                key_added = False
                for res in deserialized_resources:
                    if res["id"] == id:
                        res["db_credentials"].append(key)
                        key_added = True
                        break
                if not key_added:
                    filtered_user = copy.deepcopy(filtered_resource)
                    if "db_credentials" in filtered_user:
                        filtered_user["db_credentials"].clear()
                        filtered_user["db_credentials"].append(key)
                    else:
                        filtered_user["db_credentials"] = []
                        filtered_user["db_credentials"].append(key)
                    if "db_credential" in filtered_user:
                        filtered_user.pop("db_credential")
                    deserialized_resources.append(filtered_user)
            return deserialized_resources


@User.filter_registry.register("api-keys")
class UserApiKeysValueFilter(ValueFilter):
    """
    Filters user resources by api_key.

    :example:

    This policy will find all user whose api_key is 'INACTIVE'

    .. code-block:: yaml

        policies:
            - name: filter-user-with-inactive-api_keys
              resource: oci.user
              filters:
                - type: api-keys
                  key: api_key.lifecycle_state
                  value: 'INACTIVE'
                  op: equal

    """

    schema = type_schema("api-keys", rinherit=ValueFilter.schema)

    def process(self, resources, event):
        if "value_type" in self.data and self.data["value_type"] == "size":
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                if "api_keys" in resource:
                    result.append(resource)
                else:
                    response = self.manager.get_client().list_api_keys(
                        user_id=params_dict["user_id"],
                    )
                    api_keys = response.data
                    if api_keys:
                        res["api_keys"] = oci.util.to_dict(api_keys)
                        result.append(res)
            return super().process(result)
        else:
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                response = self.manager.get_client().list_api_keys(
                    user_id=params_dict["user_id"],
                )
                api_keys = response.data
                if api_keys:
                    for api_key in api_keys:
                        res["api_key"] = oci.util.to_dict(api_key)
                        result.append(res)
            filtered_resources = super().process(result)
            deserialized_resources = []
            for filtered_resource in filtered_resources:
                id = filtered_resource["id"]
                key = filtered_resource["api_key"]
                key_added = False
                for res in deserialized_resources:
                    if res["id"] == id:
                        res["api_keys"].append(key)
                        key_added = True
                        break
                if not key_added:
                    filtered_user = copy.deepcopy(filtered_resource)
                    if "api_keys" in filtered_user:
                        filtered_user["api_keys"].clear()
                        filtered_user["api_keys"].append(key)
                    else:
                        filtered_user["api_keys"] = []
                        filtered_user["api_keys"].append(key)
                    if "api_key" in filtered_user:
                        filtered_user.pop("api_key")
                    deserialized_resources.append(filtered_user)
            return deserialized_resources


@User.filter_registry.register("auth-tokens")
class UserAuthTokensValueFilter(ValueFilter):
    """
    Filters user resources by auth_token.

    :example:

    This policy will find all user whose auth_token is 'INACTIVE'

    .. code-block:: yaml

        policies:
            - name: filter-user-with-inactive-auth_tokens
              resource: oci.user
              filters:
                - type: auth-tokens
                  key: auth_token.lifecycle_state
                  value: 'INACTIVE'
                  op: equal

    """

    schema = type_schema("auth-tokens", rinherit=ValueFilter.schema)

    def process(self, resources, event):
        if "value_type" in self.data and self.data["value_type"] == "size":
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                if "auth_tokens" in resource:
                    result.append(resource)
                else:
                    response = self.manager.get_client().list_auth_tokens(
                        user_id=params_dict["user_id"],
                    )
                    auth_tokens = response.data
                    if auth_tokens:
                        res["auth_tokens"] = oci.util.to_dict(auth_tokens)
                        result.append(res)
            return super().process(result)
        else:
            result = []
            for resource in resources:
                params_dict = {}
                params_dict["user_id"] = resource["id"]
                res = resource
                response = self.manager.get_client().list_auth_tokens(
                    user_id=params_dict["user_id"],
                )
                auth_tokens = response.data
                if auth_tokens:
                    for auth_token in auth_tokens:
                        res["auth_token"] = oci.util.to_dict(auth_token)
                        result.append(res)
            filtered_resources = super().process(result)
            deserialized_resources = []
            for filtered_resource in filtered_resources:
                id = filtered_resource["id"]
                key = filtered_resource["auth_token"]
                key_added = False
                for res in deserialized_resources:
                    if res["id"] == id:
                        res["auth_tokens"].append(key)
                        key_added = True
                        break
                if not key_added:
                    filtered_user = copy.deepcopy(filtered_resource)
                    if "auth_tokens" in filtered_user:
                        filtered_user["auth_tokens"].clear()
                        filtered_user["auth_tokens"].append(key)
                    else:
                        filtered_user["auth_tokens"] = []
                        filtered_user["auth_tokens"].append(key)
                    if "auth_token" in filtered_user:
                        filtered_user.pop("auth_token")
                    deserialized_resources.append(filtered_user)
            return deserialized_resources
