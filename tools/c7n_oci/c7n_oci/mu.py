import json
import logging
import os
import re
from abc import ABC, abstractmethod

import oci
import yaml
from c7n_oci.constants import COMPARTMENT_IDS
from oci.events.models import ActionDetailsList, CreateFaaSActionDetails, CreateRuleDetails

from c7n.utils import local_session
from c7n.version import version

log = logging.getLogger('custodian.oci.serverless')


def is_resource_exists(resource):
    return resource and resource[0].freeform_tags.get('SourceTool') == 'Custodian'


class FunctionImageHandler:
    def __init__(self, session, tenancy):
        self.session = session
        self.tenancy = tenancy

    def initialize(self):
        self.artificats_client = self.session.client('oci.artifacts.ArtifactsClient')
        self.storage_client = self.session.client('oci.object_storage.ObjectStorageClient')
        self.identity_client = self.session.client('oci.identity.IdentityClient')

        # Importing here to avoid docker dependency at oracle function runtime
        import docker

        self.docker_client = docker.from_env()
        self.repo_name = "cloudcustodian/c7n-oci"
        self.repo_namespace = self._get_namespace()
        self.oci_repo = f"{self._get_region_key()}.ocir.io"
        self.ocir_repo_path = f"{self.oci_repo}/{self.repo_namespace}/{self.repo_name}"
        self.tag = "latest"
        self.ocir_image_name = f"{self.ocir_repo_path}:{self.tag}"
        self.docker_hub_image_name = f"{self.repo_name}:{self.tag}"
        self._oci_repo_login()

    def _oci_repo_login(self):
        response = self.identity_client.get_user(self.session.get_config()["user"])
        self.docker_client.login(
            username=f"{self.repo_namespace}/{response.data.name}",
            password=os.environ['OCI_AUTH_TOKEN'],
            registry=self.oci_repo,
        )

    def _get_namespace(self):
        return self.storage_client.get_namespace().data

    def _get_region_key(self):
        region_key = None
        data = self.identity_client.list_region_subscriptions(self.tenancy).data
        for region in data:
            if region.region_name == self.session.get_config()['region']:
                region_key = region.region_key.lower()

        if region_key:
            return region_key
        else:
            raise ValueError(
                f"Region {self.session.get_config()['region']} is not matching with \
                    any subscribed region."
            )

    def pull(self):
        log.debug("Pulling the image: %s", self.docker_hub_image_name)
        for line in self.docker_client.api.pull(
            self.docker_hub_image_name, tag=self.tag, stream=True, decode=True
        ):
            if "status" in line:
                log.debug("%s id:%s" % (line["status"], line.get("id", "n/a")))
            elif "error" in line:
                log.warning("Pull error %s" % (line,))
                raise RuntimeError("Docker Pull Failed\n %s" % (line,))
            else:
                log.info("other %s" % (line,))

    def retag(self):
        log.debug("Tagging the image: %s:%s", self.ocir_repo_path, self.tag)
        source_image = self.docker_client.images.get(self.docker_hub_image_name)
        source_image.tag(repository=self.ocir_repo_path, tag=self.tag)

    def push(self):
        log.debug("Pushing the image: %s:%s", self.ocir_repo_path, self.tag)
        self.docker_client.images.push(repository=self.ocir_repo_path, tag=self.tag)
        for line in self.docker_client.images.push(
            repository=self.ocir_repo_path, tag=self.tag, stream=True, decode=True
        ):
            if "status" in line:
                log.debug("%s id:%s" % (line["status"], line.get("id", "n/a")))
            elif "error" in line:
                log.warning("Push error %s" % (line,))
                raise RuntimeError("Docker Push Failed\n %s" % (line,))
            else:
                log.info("other %s" % (line,))

    def get_image_digest(self, image_name):
        # Importing here to avoid docker dependency at oracle function runtime
        import docker

        image = None
        try:
            image = self.docker_client.images.get_registry_data(image_name)
            if image:
                return image.attrs['Descriptor']["digest"]
        except docker.errors.NotFound:  # noqa
            log.debug(f"{image_name} is not found")
            # If image is not found on docker hub then it is handled in the calling function.
            # If it's not found in OCI tenancy then it means it needs to be uploaded to the tenancy.
            # it is handled in the calling function

    def compare_image_digest(self):
        latest_public_image_digest = self.get_image_digest(self.docker_hub_image_name)
        if not latest_public_image_digest:
            raise ValueError("Cloud Custodian docker image is not found")
        oci_image_digest = self.get_image_digest(f"{self.ocir_repo_path}:{self.tag}")
        return latest_public_image_digest == oci_image_digest


class PermissionManager:
    def __init__(self, session, tenancy_id):
        self.session = session
        self.identity_client = self.session.client('oci.identity.IdentityClient')
        self.dynamic_group_name = "custodian-fn-{}"
        self.tenancy_id = tenancy_id
        self.oci_policy_name = "custodian-function-policy"

    def add_permissions(self, compartment_id, fn_id):
        group_name = self.dynamic_group_name.format(compartment_id)
        group_data = self.get_dynamic_groups(self.tenancy_id, group_name)
        if is_resource_exists(group_data):
            # dynamic group for this compartment exits add new function in it.
            fn_ids = []
            matching_rule = group_data[0].matching_rule
            if matching_rule:
                fn_ids = self._get_func_id_from_rule(matching_rule)

            fn_ids.append(fn_id)
            matching_rule = self._construct_matching_rule(fn_ids)
            self._update_dynamic_group(group_data[0].id, matching_rule)
        else:
            # create the dynamic group and add the new function
            matching_rule = self._construct_matching_rule([fn_id])
            self._create_dynamic_group(compartment_id, group_name, matching_rule)

            # creation/updation of policy required for new dynamic group
            policy_data = self.get_oci_policy(self.tenancy_id)
            if is_resource_exists(policy_data):
                compartments = []
                statements = policy_data[0].statements
                if statements:
                    compartments = self._get_compartments_from_statement(statements)
                    if compartment_id not in compartments:
                        statements.extend(self._construct_statements([compartment_id]))
                        self.update_oci_policy(policy_data[0].id, statements)
            else:
                statements = self._construct_statements([compartment_id])
                self.create_oci_policy(statements)

    def get_dynamic_groups(self, tenancy_id, group_name):
        response = self.identity_client.list_dynamic_groups(tenancy_id, name=group_name)
        return response.data

    def get_oci_policy(self, tenancy_id):
        response = self.identity_client.list_policies(tenancy_id, name=self.oci_policy_name)
        return response.data

    def _get_compartments_from_statement(self, statements):
        return [
            re.search(r"compartment id\s+(.+)", statement).group(1)
            for statement in statements
            if re.search(r"compartment id\s+(.+)", statement)
        ]

    def remove_permissions(self, compartment_ids, fn_ids):
        for compartment_id in compartment_ids:
            group_name = self.dynamic_group_name.format(compartment_id)
            response = self.identity_client.list_dynamic_groups(self.tenancy_id, name=group_name)
            group_data = response.data
            if is_resource_exists(group_data):
                # remove function id from the dynamic group
                matching_rule = group_data[0].matching_rule
                if matching_rule:
                    all_fn_ids = self._get_func_id_from_rule(matching_rule)
                    remove_fn_ids = list(set(all_fn_ids) - set(fn_ids))

                    if remove_fn_ids:
                        try:
                            matching_rule = self._construct_matching_rule(remove_fn_ids)
                            self._update_dynamic_group(group_data[0].id, matching_rule)
                        except Exception as e:
                            log.error(
                                "Error occured while removing deleted function from dynamic group"
                            )
                            log.exception(e)
                    else:
                        try:
                            self.delete_dynamic_group(group_data[0].id)
                        except Exception as e:
                            log.error("Error occured while deleting dynamic group")
                            log.exception(e)

        # update/delete the policy since dynamic group deleted
        res = self.identity_client.list_policies(self.tenancy_id, name=self.oci_policy_name)
        policy_data = res.data
        if is_resource_exists(policy_data):
            statements = policy_data[0].statements
            if statements:
                compartments = self._get_compartments_from_statement(statements)
                compartments = list(set(compartments) - set(compartment_ids))
                if compartments:
                    try:
                        statements = self._construct_statements(compartments)
                        self.update_oci_policy(policy_data[0].id, statements)
                    except Exception as e:
                        log.error("Error occured while removing compartment from policy")
                        log.exception(e)
                else:
                    # if there is no statement left in the policy then it can be removed
                    try:
                        self.delete_oci_policy(policy_data[0].id)
                    except Exception as e:
                        log.error("Error occured while deleting policy")
                        log.exception(e)

    def _get_func_id_from_rule(self, matching_rule):
        pat = r"resource\.id='([^']+)'"
        return re.findall(pat, matching_rule)

    def _create_dynamic_group(self, compartment_id, group_name, matching_rule):
        log.debug("Creating dynamic group: %s", group_name)
        resp = self.identity_client.create_dynamic_group(
            create_dynamic_group_details=oci.identity.models.CreateDynamicGroupDetails(
                compartment_id=self.tenancy_id,
                description=f"Dynamic group for custodian functions of \
                    compartment {compartment_id}. It is managed by custodian tool, \
                        Please DO NOT DELETE OR UPDATE.",
                freeform_tags={'SourceTool': 'Custodian'},
                matching_rule=matching_rule,
                name=group_name,
            )
        )
        return resp.data.id

    def _update_dynamic_group(self, group_id, matching_rule):
        log.debug("Updating dynamic group: %s", str(group_id))
        resp = self.identity_client.update_dynamic_group(
            dynamic_group_id=group_id,
            update_dynamic_group_details=oci.identity.models.UpdateDynamicGroupDetails(
                matching_rule=matching_rule
            ),
        )
        return resp

    def delete_dynamic_group(self, group_id):
        self.identity_client.delete_dynamic_group(group_id)

    def _construct_matching_rule(self, fn_ids):
        condition = ", ".join([f"resource.id='{fn_id}'" for fn_id in fn_ids])
        return "Any{%s}" % condition

    def create_oci_policy(self, statements):
        log.debug("Creating policy: %s", self.oci_policy_name)
        self.identity_client.create_policy(
            create_policy_details=oci.identity.models.CreatePolicyDetails(
                compartment_id=self.tenancy_id,
                name=self.oci_policy_name,
                statements=statements,
                description="Custodian policy to allow function to access resources. \
                    It is managed by custodian tool, Please DO NOT DELETE OR UPDATE.",
                freeform_tags={'SourceTool': 'Custodian'},
            )
        )

    def update_oci_policy(self, policy_id, statements):
        log.debug("Updating policy: %s", self.oci_policy_name)
        self.identity_client.update_policy(
            policy_id,
            update_policy_details=oci.identity.models.UpdatePolicyDetails(statements=statements),
        )

    def delete_oci_policy(self, policy_id):
        log.debug("Deleting policy: %s", self.oci_policy_name)
        self.identity_client.delete_policy(policy_id)

    def _construct_statements(self, compartment_ids):
        return [
            (
                f"allow dynamic-group {self.dynamic_group_name.format(compartment_id)} to"
                f" manage all-resources in compartment id {compartment_id}"
            )
            for compartment_id in compartment_ids
        ]


class FunctionManager:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session = local_session(session_factory)
        self.tenancy_id = self.session.get_config()['tenancy']
        self.client = self.session.client('oci.functions.FunctionsManagementClient')
        self.event_rule = EventRule(self.session)
        self.image_handler = FunctionImageHandler(self.session, self.tenancy_id)
        self.permission_manager = PermissionManager(self.session, self.tenancy_id)
        self.compartments = self.get_compartments()

    def list_applications(self, compartement_id, name=None):
        response = self.client.list_applications(compartement_id, display_name=name)
        return response.data

    def create_application(self, compartment_id, func):
        app_details = oci.functions.models.CreateApplicationDetails(
            compartment_id=compartment_id,
            display_name=func.display_name,
            subnet_ids=func.subnet_ids,
            freeform_tags=func.freeform_tags,
        )
        log.debug("Creating application: %s", func.display_name)
        result = self.client.create_application(app_details)
        return result.data.id

    def update_application(self, app_id, func):
        app_details = oci.functions.models.UpdateApplicationDetails(
            freeform_tags=func.freeform_tags,
        )
        log.debug("Updating application: %s", func.display_name)
        self.client.update_application(app_id, update_application_details=app_details)

    def delete_application(self, app_id):
        try:
            log.debug("Deleting application: %s", str(app_id))
            return self.client.delete_application(app_id)
        except Exception as e:
            log.error(f"Error occured while deleting the application {str(app_id)}")
            log.exception(e)

    def has_app_changed(self, func, existing_app):
        for key in ['freeform_tags']:
            if getattr(func, key) != getattr(existing_app, key):
                return True
        return False

    def list_functions(self, app_id):
        response = self.client.list_functions(app_id)
        return response.data

    def get_function(self, fn_id):
        response = self.client.get_function(fn_id)
        return response.data

    def create_function(self, app_id, func, ocir_image_name):
        config = self._get_func_config(func)
        func_details = oci.functions.models.CreateFunctionDetails(
            display_name=func.display_name,
            application_id=app_id,
            memory_in_mbs=func.memory_in_mbs,
            image=ocir_image_name,
            config=config,
            freeform_tags=func.freeform_tags,
            timeout_in_seconds=func.timeout_in_seconds,
        )
        log.debug("Creating function: %s", func.display_name)
        result = self.client.create_function(create_function_details=func_details)
        return result.data.id

    def update_function(self, fn_id, func, ocir_image_name):
        config = self._get_func_config(func)
        func_details = oci.functions.models.UpdateFunctionDetails(
            memory_in_mbs=func.memory_in_mbs,
            image=ocir_image_name,
            config=config,
            freeform_tags=func.freeform_tags,
            timeout_in_seconds=func.timeout_in_seconds,
        )
        log.debug("Updating function: %s", func.display_name)
        self.client.update_function(fn_id, func_details)

    def delete_function(self, fn_id):
        try:
            log.debug("Deleting function: %s", str(fn_id))
            return self.client.delete_function(fn_id)
        except Exception as e:
            log.error(f"Error occured while deleting the function {str(fn_id)}")
            log.exception(e)

    def get_exec_options(self, options):
        """preserve cli output options into serverless environment."""
        d = {}
        for k in ('log_group', 'output_dir'):
            if options.get(k):
                d[k] = options[k]
        d['region'] = self.session.get_config()['region']
        # ignore local fs/dir output paths
        if 'output_dir' in d and '://' not in d['output_dir']:
            d.pop('output_dir')
        return json.dumps(d)

    def _get_func_config(self, func):
        policy_yaml_string = yaml.dump({"policies": [func.policy.data]})
        return {
            'policy': policy_yaml_string,
            'execution-options': self.get_exec_options(func.policy.options),
            'OCI_CLI_AUTH': 'resource_principal',
            'OCI_FUNCTION_POLICY_RUNNING': 'yes',
        }

    def has_func_changed(self, func, fn_id):
        existing_fn = self.get_function(fn_id)
        config = self._get_func_config(func)
        if config != existing_fn.config:
            return True
        for key in ['memory_in_mbs', 'freeform_tags', 'timeout_in_seconds']:
            if getattr(func, key) != getattr(existing_fn, key):
                return True
        return False

    def get_compartments(self):
        compartments = []
        comps_env_var = os.environ.get(COMPARTMENT_IDS)
        if comps_env_var:
            compartments = comps_env_var.split(",")
        else:
            compartments = [self.tenancy_id]
        log.debug("Compartments : %s", str(compartments))
        return compartments

    def publish_image(self):
        self.image_handler.initialize()
        is_image_same = self.image_handler.compare_image_digest()
        if not is_image_same:
            self.image_handler.pull()
            self.image_handler.retag()
            self.image_handler.push()
        return is_image_same, self.image_handler.ocir_image_name

    def create_or_update(self, func, is_image_same, ocir_image_name):
        status = None
        for compartment in self.compartments:
            app_details = self.list_applications(compartment, func.display_name)
            if is_resource_exists(app_details):
                log.debug("Starting function updation for the compartment %s", compartment)
                app_id = app_details[0].id
                if self.has_app_changed(func, app_details[0]):
                    self.update_application(app_id, func)
                fn_details = self.list_functions(app_id)
                if is_resource_exists(fn_details):
                    fn_id = fn_details[0].id
                    if not is_image_same or self.has_func_changed(func, fn_id):
                        self.update_function(fn_details[0].id, func, ocir_image_name)
                event_rule_details = self.event_rule.list_event_rules(
                    compartment, func.display_name
                )
                if is_resource_exists(event_rule_details):
                    if self.event_rule.has_event_rule_changed(func, event_rule_details[0]):
                        self.event_rule.update(event_rule_details[0].id, func)
                log.debug("Completed function updation for the compartment %s", compartment)
                status = "UPDATED"
            else:
                try:
                    log.debug("Starting function creation for the compartment %s", compartment)
                    app_id = self.create_application(compartment, func)
                    fn_id = self.create_function(app_id, func, ocir_image_name)
                    self.event_rule.create(compartment, fn_id, func)
                    self.permission_manager.add_permissions(compartment, fn_id)
                    status = "CREATED"
                    log.debug("Completed function creation for the compartment %s", compartment)
                except Exception as e:
                    status = "ERROR"
                    log.error("Error occurred while function creation. Rolling back")
                    log.exception(e)
                    # rollback
                    self.remove(func)
                    raise e
        return status

    def publish(self, func):
        is_image_updated, ocir_image_name = self.publish_image()
        status = self.create_or_update(func, is_image_updated, ocir_image_name)
        log.info("Function %s %s successfully", func.display_name, status)

    def remove(self, func):
        log.info("Removing Oracle function %s and dependent objects", func.display_name)
        remove_compartment = []
        remove_fn = []
        for compartment in self.compartments:
            app = self.list_applications(compartment, func.display_name)
            if is_resource_exists(app):
                fn = self.list_functions(app[0].id)
                if is_resource_exists(fn):
                    self.delete_function(fn[0].id)
                    remove_fn.append(fn[0].id)
                else:
                    log.debug(f"No function found for application {func.display_name}")
                self.delete_application(app[0].id)
                remove_compartment.append(compartment)
                event_rule = self.event_rule.list_event_rules(compartment, func.display_name)
                if event_rule:
                    self.event_rule.remove(event_rule[0].id)
                else:
                    log.debug(f"No event_rule found for application {func.display_name}")
            else:
                log.debug(f"No application found with name {func.display_name}")
        if remove_compartment or remove_fn:
            self.permission_manager.remove_permissions(remove_compartment, remove_fn)
        log.info("Removed Oracle function %s and dependent objects", func.display_name)


class AbstractFunction(ABC):
    """Abstract base class for cloud functions."""

    @property
    @abstractmethod
    def display_name(self):
        """The display name of the function.
        The display name must be unique within the application containing the function"""

    @property
    @abstractmethod
    def memory_in_mbs(self):
        """Maximum usable memory for the function (MiB)"""

    @property
    @abstractmethod
    def timeout_in_seconds(self):
        """Timeout for executions of the function. Value in seconds."""

    @property
    @abstractmethod
    def freeform_tags(self):
        """Free-form tags for this Function. Each tag is a simple key-value pair"""

    @property
    @abstractmethod
    def subnet_ids(self):
        """The `OCID`__s of the subnets in which to run functions in the application."""

    @property
    @abstractmethod
    def events(self):
        """Events required for event rule creation."""


class PolicyFunction(AbstractFunction):
    def __init__(self, policy):
        self.policy = policy

    @property
    def display_name(self):
        prefix = self.policy.data['mode'].get('function-prefix', 'custodian-')
        return "%s%s" % (prefix, self.policy.name)

    event_name = display_name

    @property
    def memory_in_mbs(self):
        return self.policy.data['mode'].get('memory', 512)

    @property
    def timeout_in_seconds(self):
        return self.policy.data['mode'].get('timeout')

    @property
    def freeform_tags(self):
        tags = {'SourceTool': 'Custodian', "custodian-info": version}
        if self.policy.data['mode'].get('freeform_tags'):
            tags.update(self.policy.data['mode'].get('freeform_tags'))
        return tags

    @property
    def subnet_ids(self):
        return self.policy.data['mode'].get('subnets')

    @property
    def events(self):
        return self.policy.data['mode'].get('events')


class EventRule:
    def __init__(self, session):
        self.session = session
        self.client = self.session.client('oci.events.EventsClient')

    def create(self, compartment_id, func_id, func):
        condition = self._get_event_rule_condition(func)
        action_list = self._get_action_list(func_id)
        rule_details = CreateRuleDetails(
            compartment_id=compartment_id,
            display_name=func.display_name,
            description='Custodian event rule',
            condition=json.dumps(condition),
            actions=action_list,
            is_enabled=True,
            freeform_tags=func.freeform_tags,
        )
        log.debug("Creating event rule: %s", func.display_name)
        response = self.client.create_rule(rule_details)
        return response.data

    def list_event_rules(self, compartment_id, name=None):
        response = self.client.list_rules(
            compartment_id, lifecycle_state="ACTIVE", display_name=name
        )
        return response.data

    def update(self, rule_id, func):
        condition = self._get_event_rule_condition(func)
        rule_details = oci.events.models.UpdateRuleDetails(
            condition=json.dumps(condition), freeform_tags=func.freeform_tags
        )
        log.debug("Updating event rule: %s", func.display_name)
        self.client.update_rule(rule_id, update_rule_details=rule_details)

    def has_event_rule_changed(self, func, existing_event_rule):
        condition = self._get_event_rule_condition(func)
        return (
            json.dumps(condition) != existing_event_rule.condition
            or func.freeform_tags != existing_event_rule.freeform_tags
        )

    def remove(self, rule_id):
        log.debug("Deleting event rule: %s", str(rule_id))
        return self.client.delete_rule(rule_id)

    def _get_event_rule_condition(self, func):
        return {
            "eventType": [
                f"{func.policy.resource_manager.resource_type.event_service_name}.{event.lower()}"
                for event in func.events
            ]
        }

    def _get_action_list(self, func_id):
        action_details = CreateFaaSActionDetails(
            action_type='FAAS',
            is_enabled=True,
            description='Custodian function action',
            function_id=func_id,
        )
        return ActionDetailsList(actions=[action_details])
