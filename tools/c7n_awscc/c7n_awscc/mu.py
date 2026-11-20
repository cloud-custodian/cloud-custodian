# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import base64
import contextlib
import json
import logging
import uuid
import os

import boto3

from c7n.mu import AWSEventBase, PolicyLambda, get_exec_options, PythonPackageArchive
from c7n.mu import _package_deps as get_dependencies
from c7n.version import version

"""
policies:
  - resource: awscc.ec2
    name: check ec2
    description: something else
    mode:
      - type: cfn-hook
        match-compliant: false
        action: FAIL | WARN
        enabled: true
        log-role: arn
        exec-role: arn
"""


PolicyHandlerTemplate = """
from c7n_awscc import handler

def run(event, context):
    return handler.handle(event, context)
"""


class HookPolicy(PolicyLambda):
    def __init__(self, policy):
        self.policy = policy
        self.archive = None

    @property
    def type_name(self):
        return hook_name(self.policy.name)

    @property
    def type_info(self):
        return self.policy.resource_manager.resource_type

    def get_hook_schema(self, include_type=False):
        schema = {
            "properties": {},
            "additionalProperties": False,
        }
        if include_type:
            schema["typeName"] = self.type_name
            schema["definitions"] = {}
        return schema

    def get_hook_metadata(self):
        info = {
            "typeName": self.type_name,
            "description": self.description,
            "sourceUrl": "https://github.com/cloud-custodian/cloud-custodian",
            "documentationUrl": "https://cloudcustodian.io/docs",
            "typeConfiguration": self.get_hook_schema(),
            "required": [],
            "additionalProperties": False,
            "handlers": {
                "preCreate": {
                    "targetNames": [self.type_info.cfn_type],
                    "permissions": list(self.policy.get_permissions()),
                },
                "preUpdate": {
                    "targetNames": [self.type_info.cfn_type],
                    "permissions": list(self.policy.get_permissions()),
                },
            },
        }
        return info

    def get_rpdk_metadata(self):
        return {
            "artifact_type": "HOOK",
            "typeName": self.type_name,
            "language": "python37",
            "runtime": "python3.7",
            "entrypoint": "c7n_hook.handlers.handle",
            # pile of random...
            "settings": {
                "protocolVersion": "2.0.0",
                "version": False,
                "subparser_name": None,
                "artifact_type": None,
                "target_schemas": [],
                "region": None,
                "verbose": 0,
                "force": False,
                "use_docker": false,
            },
        }

    def get_cfn_metadata(self):
        return {
            "plugin-name": "custodian",
            "cli-version": "na",
            "plugin-tool-version": version,
        }

    def get_target_info(self):
        schema = dict(self.policy.resource_manager.schema)
        schema.pop("handlers", None)
        return {
            self.type_info.cfn_type: {
                "TargetName": self.type_info.cfn_type,
                "TargetType": "RESOURCE",
                "Schema": schema,
                "ProvisioningType": "FULLY_MUTABLE",
                "SchemaFileAvailable": True,
                "IsCfnRegistrySupportedType": True,
            }
        }

    def get_archive(self, include_deps=True):
        archive = PythonPackageArchive()
        # The format of these things is baroque..
        # we have a zip file containing another zip file and
        # bunch of json files with redundant information recorded in
        # multiple places.

        archive.add_contents(
            "src/c7n_hook/config.json",
            json.dumps(
                {
                    "execution-options": get_exec_options(self.policy.options),
                    "policies": [self.policy.data],
                },
                indent=2,
            ),
        )
        archive.add_contents("src/c7n_hook/__init__.py", "")
        archive.add_contents("src/c7n_hook/handlers.py", PolicyHandlerTemplate)

        if include_deps:
            deps = get_dependencies("boto3")
            deps.append("c7n_awscc")
            deps.remove("python-dateutil")
            deps.append("dateutil")
            dep_archive = custodian_archive(packages=deps)
            dep_archive.close()
            self.add_contents("ResourceProvider.zip", dep_archive.get_bytes())

        # bespoke cfn extension files
        archive.add_json("target-info.json", self.get_target_info())
        # export the exact same content to a different file :shrug:
        archive.add_json(
            "target-schemas/%s.json"
            % "-".join([t.lower() for t in self.type_info.cfn_type.split("::")]),
            self.policy.resource_manager.schema,
        )
        archive.add_json("configuration-schema.json", self.get_hook_metadata(True))
        archive.add_json("schema.json", self.get_hook_config())
        archive.add_json(".rpdk-config", self.get_rpdk_metadata())
        archive.add_json(".cfn_metadata.json", self.get_cfn_metadata())
        archive.close()
        return archive


def hook_name(policy_name):
    type_name = "".join([t.title() for t in policy_name.split("-")])
    return f"CloudCustodian::{type_name}::Hook"


class HookManager(AWSEventBase):

    client_service = "cloudformation"

    @staticmethod
    def delta(src, tgt):
        return

    def get(self, name):
        result = self.client.describe_type(hook_name(name))
        result.pop("ResponseMetadata")
        return result

    def add(self, func):
        active_hook_info = self.get(func.name)
        target_hook_info = self.get_hook_info(func)
        if not self.delta(active_hook_info, target_hook_info):
            return

        s3_url = self.upload()
        type_info = self.get_type_info(func)

        token = self.client.register_type(
            Type="HOOK",
            TypeName=hook_name(func.name),
            SchemaHandlerPackage=s3_url,
            LoggingConfig={
                "LogRoleArn": self.data["log-role"],
                "LogGroupName": "/cloud-custodian/hooks/%s" % func.name,
            },
            ExecutionRoleArn=self.data["exec-role"],
        ).get("RegistrationToken")

        type_arn = self.wait_for_registration(token)
        self.client.set_type_configuration(
            TypeArn=type_arn,
            Configuration=json.dumps(
                {
                    "CloudFormationConfiguration": {
                        "HookConfiguration": {
                            "TargetStacks": "ALL",
                            "FailureMode": self.data["action"],
                            "Properties": {},
                        }
                    }
                }
            ),
        )

    def remove(self, func, func_deleted=True):
        pass

    def get_hook_info(self, func):
        pass
