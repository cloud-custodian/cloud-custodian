# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import argparse
import functools
import logging
from os import path

import jsonschema
import yaml
from c7n_mailer import deploy, utils
from c7n_mailer.azure_mailer import deploy as azure_deploy

# from c7n_mailer.gcp_mailer import deploy as gcp_deploy
from c7n_mailer.utils import session_factory, get_processor, get_provider, Providers

AZURE_KV_SECRET_SCHEMA = {
    "type": "object",
    "properties": {"type": {"enum": ["azure.keyvault"]}, "secret": {"type": "string"}},
    "required": ["type", "secret"],
    "additionalProperties": False,
}

GCP_SECRET_SCHEMA = {
    "type": "object",
    "properties": {"type": {"enum": ["gcp.secretmanager"]}, "secret": {"type": "string"}},
    "required": ["type", "secret"],
    "additionalProperties": False,
}

SECURED_STRING_SCHEMA = {"oneOf": [{"type": "string"}, AZURE_KV_SECRET_SCHEMA, GCP_SECRET_SCHEMA]}

CONFIG_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema",
    "id": "https://schema.cloudcustodian.io/v0/mailer.json",
    "type": "object",
    "additionalProperties": False,
    "required": ["queue_url"],
    "properties": {
        "queue_url": {"type": "string"},
        "endpoint_url": {"type": "string"},
        "from_address": {"type": "string"},
        "additional_email_headers": {
            "type": "object",
            "patternProperties": {
                "": {"type": "string"},
            },
        },
        "contact_tags": {"type": "array", "items": {"type": "string"}},
        "org_domain": {"type": "string"},
        # Standard Lambda Function Config
        "region": {"type": "string"},
        "role": {"type": "string"},
        "runtime": {"type": "string"},
        "memory": {"type": "integer"},
        "timeout": {"type": "integer"},
        "subnets": {"type": "array", "items": {"type": "string"}},
        "security_groups": {"type": "array", "items": {"type": "string"}},
        "dead_letter_config": {"type": "object"},
        "lambda_name": {"type": "string"},
        "lambda_description": {"type": "string"},
        "lambda_tags": {"type": "object"},
        "lambda_schedule": {"type": "string"},
        # Azure Function Config
        "function_properties": {
            "type": "object",
            "identity": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {"enum": ["Embedded", "SystemAssigned", "UserAssigned"]},
                    "client_id": {"type": "string"},
                    "id": {"type": "string"},
                },
            },
            "appInsights": {
                "type": "object",
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "name": "string",
                            "location": "string",
                            "resourceGroupName": "string",
                        },
                    },
                ],
            },
            "storageAccount": {
                "type": "object",
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "name": "string",
                            "location": "string",
                            "resourceGroupName": "string",
                        },
                    },
                ],
            },
            "servicePlan": {
                "type": "object",
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "name": "string",
                            "location": "string",
                            "resourceGroupName": "string",
                            "skuTier": "string",
                            "skuName": "string",
                        },
                    },
                ],
            },
        },
        # GCP Cloud Function Config # TODO:
        # 'function_schedule': {'type': 'string'},
        # 'function_skuCode': {'type': 'string'},
        # 'function_sku': {'type': 'string'},
        "email_base_url": {"type": "string"},
        # Mailer Infrastructure Config
        "cache_engine": {"type": "string"},
        "smtp_server": {"type": "string"},
        "smtp_port": {"type": "integer"},
        "smtp_ssl": {"type": "boolean"},
        "smtp_username": {"type": "string"},
        "smtp_password": SECURED_STRING_SCHEMA,
        "ldap_email_key": {"type": "string"},
        "ldap_uid_tags": {"type": "array", "items": {"type": "string"}},
        "debug": {"type": "boolean"},
        "ldap_uid_regex": {"type": "string"},
        "ldap_uri": {"type": "string"},
        "ldap_bind_dn": {"type": "string"},
        "ldap_bind_user": {"type": "string"},
        "ldap_uid_attribute": {"type": "string"},
        "ldap_manager_attribute": {"type": "string"},
        "ldap_email_attribute": {"type": "string"},
        "ldap_bind_password_in_kms": {"type": "boolean"},
        "ldap_bind_password": SECURED_STRING_SCHEMA,
        "cross_accounts": {"type": "object"},
        "ses_region": {"type": "string"},
        "ses_role": {"type": "string"},
        "redis_host": {"type": "string"},
        "redis_port": {"type": "integer"},
        "datadog_api_key": {"type": "string"},  # TODO: encrypt with KMS?
        "datadog_application_key": {"type": "string"},  # TODO: encrypt with KMS?
        "slack_token": {"type": "string"},
        "slack_webhook": {"type": "string"},
        "sendgrid_api_key": SECURED_STRING_SCHEMA,
        "splunk_hec_url": {"type": "string"},
        "splunk_hec_token": {"type": "string"},
        "splunk_remove_paths": {"type": "array", "items": {"type": "string"}},
        "splunk_actions_list": {"type": "boolean"},
        "splunk_max_attempts": {"type": "integer"},
        "splunk_hec_max_length": {"type": "integer"},
        "splunk_hec_sourcetype": {"type": "string"},
        # MS Graph API config
        "graph_token_endpoint": {"type": "string"},
        "graph_sendmail_endpoint": {"type": "string"},
        "graph_client_id": {"type": "string"},
        "graph_client_secret": SECURED_STRING_SCHEMA,
        # Jira config
        "jira_url": {"type": "string"},
        "jira_username": {"type": "string"},
        "jira_token": SECURED_STRING_SCHEMA,
        "jira_custom_fields": {"type": "object"},
        # SDK Config
        "profile": {"type": "string"},
        "http_proxy": {"type": "string"},
        "https_proxy": {"type": "string"},
        # Mapping account / emails
        "account_emails": {"type": "object"},
    },
}


def get_logger(debug=False):
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    if debug:
        logging.getLogger("botocore").setLevel(logging.DEBUG)
        debug_logger = logging.getLogger("custodian-mailer")
        debug_logger.setLevel(logging.DEBUG)
        return debug_logger
    else:
        return logging.getLogger("custodian-mailer")


def get_and_validate_mailer_config(args):
    with open(args.config) as fh:
        config = yaml.load(fh.read(), Loader=yaml.SafeLoader)
    jsonschema.validate(config, CONFIG_SCHEMA)
    utils.setup_defaults(config)
    return config


def get_c7n_mailer_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", required=True, help="mailer.yml config file")
    debug_help_msg = "sets c7n_mailer logger to debug, for maximum output (the default is INFO)"
    parser.add_argument("--debug", action="store_true", help=debug_help_msg)
    max_num_processes_help_msg = "will run the mailer in parallel, integer of max processes allowed"
    parser.add_argument("--max-num-processes", type=int, help=max_num_processes_help_msg)
    templates_folder_help_msg = "message templates folder location"
    parser.add_argument("-t", "--templates", help=templates_folder_help_msg)
    group = parser.add_mutually_exclusive_group(required=True)
    update_lambda_help_msg = "packages your c7n_mailer, uploads the zip to aws lambda as a function"
    group.add_argument("--update-lambda", action="store_true", help=update_lambda_help_msg)
    run_help_msg = "run c7n-mailer locally, process sqs messages and send emails or sns messages"
    group.add_argument("--run", action="store_true", help=run_help_msg)
    return parser


def run_mailer_in_parallel(processor, max_num_processes):
    max_num_processes = int(max_num_processes)
    if max_num_processes < 1:
        raise Exception
    processor.max_num_processes = max_num_processes
    processor.run(parallel=True)


def main():
    parser = get_c7n_mailer_parser()
    args = parser.parse_args()
    mailer_config = get_and_validate_mailer_config(args)
    args_dict = vars(args)
    logger = get_logger(debug=args_dict.get("debug", False))

    module_dir = path.dirname(path.abspath(__file__))
    default_templates = [
        path.abspath(path.join(module_dir, "msg-templates")),
        path.abspath(path.join(module_dir, "..", "msg-templates")),
        path.abspath("."),
    ]
    templates = args_dict.get("templates", None)
    if templates:
        default_templates.append(path.abspath(path.expanduser(path.expandvars(templates))))

    mailer_config["templates_folders"] = default_templates

    provider = get_provider(mailer_config)
    if args_dict.get("update_lambda"):
        if args_dict.get("debug"):
            print("\n** --debug is only supported with --run, not --update-lambda **\n")
            return
        if args_dict.get("max_num_processes"):
            print(
                "\n** --max-num-processes is only supported " "with --run, not --update-lambda **\n"
            )
            return

        if provider == Providers.Azure:
            azure_deploy.provision(mailer_config)
        # elif provider == Providers.GCP:  # TODO:
        #     gcp_deploy.provision(mailer_config)
        elif provider == Providers.AWS:
            deploy.provision(mailer_config, functools.partial(session_factory, mailer_config))

    if args_dict.get("run"):
        max_num_processes = args_dict.get("max_num_processes")

        # Select correct processor
        processor = get_processor(mailer_config, logger)

        # Execute
        if max_num_processes:
            run_mailer_in_parallel(processor, max_num_processes)
        else:
            processor.run()


if __name__ == "__main__":
    main()
