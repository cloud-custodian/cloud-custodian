# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from boto3 import Session

from .utils import get_message_subject, get_resource_tag_targets, get_rendered_jinja


class SnsDelivery:
    def __init__(self, config, session, logger):
        self.config = config
        self.logger = logger
        self.aws_sts = session.client("sts")
        self.sns_cache = {}

    def deliver_sns_messages(self, packaged_sns_messages, sqs_message):
        for packaged_sns_message in packaged_sns_messages:
            topic = packaged_sns_message["topic"]
            subject = packaged_sns_message["subject"]
            sns_message = packaged_sns_message["sns_message"]
            self.deliver_sns_message(topic, subject, sns_message, sqs_message)

    def get_valid_sns_from_list(self, possible_sns_values):
        sns_addresses = []
        for target in possible_sns_values:
            if self.target_is_sns(target):
                sns_addresses.append(target)
        return sns_addresses

    def get_sns_message_package(self, sqs_message, policy_sns_address, subject, resources):
        rendered_jinja_body = get_rendered_jinja(
            policy_sns_address,
            sqs_message,
            resources,
            self.logger,
            "template",
            "default",
            self.config["templates_folders"],
        )
        return {"topic": policy_sns_address, "subject": subject, "sns_message": rendered_jinja_body}

    def get_sns_message_packages(self, sqs_message):
        sns_to_resources_map = self.get_sns_addrs_to_resources_map(sqs_message)
        subject = get_message_subject(sqs_message)
        sns_addrs_to_rendered_jinja_messages = []
        # take the map with lists of resources, and jinja render them and add them
        # to sns_addrs_to_rendered_jinja_messages as an sns_message package
        for sns_topic, resources in sns_to_resources_map.items():
            sns_addrs_to_rendered_jinja_messages.append(
                self.get_sns_message_package(sqs_message, sns_topic, subject, resources)
            )

        if sns_addrs_to_rendered_jinja_messages == []:
            self.logger.debug("Found no sns addresses, delivering no messages.")
        return sns_addrs_to_rendered_jinja_messages

    def get_sns_addrs_to_resources_map(self, sqs_message):
        policy_to_sns_addresses = self.get_valid_sns_from_list(sqs_message["action"].get("to", []))
        sns_addrs_to_resources_map = {}
        # go over all sns_addresses from the to field
        for policy_sns_address in policy_to_sns_addresses:
            sns_addrs_to_resources_map[policy_sns_address] = sqs_message["resources"]
        # get sns topics / messages inside resource-owners tags
        for resource in sqs_message["resources"]:
            resource_owner_tag_keys = self.config.get("contact_tags", [])
            possible_sns_tag_values = get_resource_tag_targets(resource, resource_owner_tag_keys)
            sns_tag_values = self.get_valid_sns_from_list(possible_sns_tag_values)
            # for each resource, get any valid sns topics, and add them to the map
            for sns_tag_value in sns_tag_values:
                # skip sns topics in tags if they're already in the to field
                if sns_tag_value in policy_to_sns_addresses:
                    continue
                sns_addrs_to_resources_map.setdefault(sns_tag_value, []).append(resource)
        return sns_addrs_to_resources_map

    def target_is_sns(self, target):
        if target.startswith("arn:aws:sns"):
            return True
        return False

    def deliver_sns_message(self, topic, subject, rendered_jinja_body, sqs_message):
        # Max length of subject in sns is 100 chars
        if len(subject) > 100:
            subject = subject[:97] + ".."
        try:
            account = topic.split(":")[4]
            if account in self.sns_cache:
                sns = self.sns_cache[account]
            else:
                # if cross_accounts isn't set, we'll try using the current credentials
                if account not in self.config.get("cross_accounts", []):
                    session = Session()
                else:
                    creds = self.aws_sts.assume_role(
                        RoleArn=self.config["cross_accounts"][account],
                        RoleSessionName="CustodianNotification",
                    )["Credentials"]
                    session = Session(
                        aws_access_key_id=creds["AccessKeyId"],
                        aws_secret_access_key=creds["SecretAccessKey"],
                        aws_session_token=creds["SessionToken"],
                    )
                self.sns_cache[account] = sns = session.client("sns")

            self.logger.info(
                "Sending account:%s policy:%s sns:%s to %s"
                % (
                    sqs_message.get("account", ""),
                    sqs_message["policy"]["name"],
                    sqs_message["action"].get("template", "default"),
                    topic,
                )
            )
            sns.publish(TopicArn=topic, Subject=subject, Message=rendered_jinja_body)
        except Exception as e:
            self.logger.warning(
                "Error policy:%s account:%s sending sns to %s \n %s"
                % (sqs_message["policy"], sqs_message.get("account", "na"), topic, e)
            )
