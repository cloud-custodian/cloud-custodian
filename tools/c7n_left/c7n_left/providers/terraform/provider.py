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
    ResultSet,
    PolicyResourceResult,
)
from .graph import TerraformGraph
from .filters import Taggable
from .variables import VariableResolver


class TerraformResourceManager(IACResourceManager):
    class resource_type:
        id = "id"

    def get_model(self):
        return self.resource_type

    def augment(self, resources, event):
        # aws is currently the only terraform provider that supports default_tags afaics
        #
        # https://github.com/hashicorp/terraform-provider-azurerm/issues/13776
        # https://github.com/hashicorp/terraform-provider-google/issues/7325
        if event.get("resource_type", "").startswith("aws_") and Taggable.is_taggable(resources):
            self.augment_provider_tags(resources, event)
        return resources

    def augment_provider_tags(self, resources, event):
        # The one resource in aws that doesn't support default_tags
        # https://registry.terraform.io/providers/hashicorp/aws/latest/docs#default_tags
        if event["resource_type"] == "aws_autoscaling_group":
            return
        provider_tags = {}
        for type_name, blocks in event["graph"].get_resources_by_type(("provider",)):
            for block in blocks:
                if block["__tfmeta"]["label"] != "aws":
                    continue
                provider_tags.update(block.get("default_tags", {}).get("tags") or {})

        if not provider_tags:
            return

        for r in resources:
            rtags = dict(provider_tags)
            if r.get("tags"):
                rtags.update(r["tags"])
            r["tags"] = rtags


TerraformResourceManager.filter_registry.register("taggable", Taggable)


class TerraformResourceMap(IACResourceMap):
    resource_class = TerraformResourceManager


@clouds.register("terraform")
class TerraformProvider(IACSourceProvider):
    display_name = "Terraform"
    resource_prefix = "terraform"
    resource_map = TerraformResourceMap(resource_prefix)
    resources = resource_map
    reporter = None

    def initialize(self, options):
        self.reporter = options.get("reporter")

    def initialize_policies(self, policies, options):
        for p in policies:
            p.data["mode"] = {"type": "terraform-source"}
        return policies

    def parse(self, source_dir, var_files=()):
        resolver = VariableResolver(source_dir, var_files, self.reporter)
        with resolver.get_variables() as var_files:
            graph = TerraformGraph(
                load_from_path(
                    source_dir,
                    vars_paths=var_files,
                    allow_downloads=True,
                ),
                source_dir,
            )
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

    def as_results(self, resources, event):
        # for any module based results, we hoist back to the top level, with references
        for idx, r in enumerate(list(resources)):
            if not r["__tfmeta"]["path"].startswith("module."):
                continue
            resources[idx] = self.resolve_module_ref(r, event["graph"])

        return ResultSet([PolicyResourceResult(r, self.policy) for r in resources])

    def resolve_module_ref(self, mod_resource, graph):
        mod_map = {}
        for _, modules in graph.get_resources_by_type("module"):
            for m in modules:
                mod_map[m["__tfmeta"]["path"]] = m

        call_stack = extract_mod_stack(mod_resource["__tfmeta"]["path"])
        ancestor = mod_map[call_stack[0]]
        ancestor["__tfmeta"].setdefault("refs", []).append(mod_resource["__tfmeta"]["path"])
        return ancestor


def extract_mod_stack(mr_path):
    call_stack = []
    parts = mr_path.split(".")
    for step in range(2, len(parts) + 1, 2):
        call_stack.append(".".join(parts[:step]))
    return call_stack
