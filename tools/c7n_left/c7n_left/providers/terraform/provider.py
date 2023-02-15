# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#

from tfparse import load_from_path

from c7n.provider import clouds
from c7n.policy import execution
from c7n.utils import type_schema

from ...core import (
    IACResourceManager,
    IACResourceMap,
    IACSourceProvider,
    IACSourceMode,
    log,
)
from .graph import TerraformGraph


class TerraformResourceManager(IACResourceManager):
    class resource_type:
        id = "id"

    def get_model(self):
        return self.resource_type


class TerraformResourceMap(IACResourceMap):
    resource_class = TerraformResourceManager


@clouds.register("terraform")
class TerraformProvider(IACSourceProvider):
    display_name = "Terraform"
    resource_prefix = "terraform"
    resource_map = TerraformResourceMap(resource_prefix)
    resources = resource_map

    def initialize_policies(self, policies, options):
        for p in policies:
            p.data["mode"] = {"type": "terraform-source"}
        return policies

    def parse(self, source_dir):
        graph = TerraformGraph(load_from_path(source_dir), source_dir)
        graph.build()
        log.debug("Loaded %d %s resources", len(graph), self.type)
        return graph

    def match_dir(self, source_dir):
        files = list(source_dir.glob("*.tf"))
        files += list(source_dir.glob("*.tf.json"))
        return files


@execution.register("terraform-source")
class TerraformSource(IACSourceMode):
    schema = type_schema("terraform-source")
