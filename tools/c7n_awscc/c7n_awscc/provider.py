# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

from c7n.registry import PluginRegistry
from c7n.provider import clouds
from c7n.resources.aws import AWS


def get_resource_map():
    return json.loads((Path(__file__).parent / "data" / "index.json").read_text())["resources"]


@clouds.register("awscc")
class AwsCloudControl(AWS):
    display_name = "AWS Cloud Control"
    resource_prefix = ("awscc",)
    resources = PluginRegistry("%s.resources" % resource_prefix)
    resource_map = get_resource_map()


resources = AwsCloudControl.resources
