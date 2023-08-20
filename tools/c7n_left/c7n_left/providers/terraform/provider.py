# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import contextlib
from pathlib import Path
import tempfile

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

    def parse(self, source_dir, var_files=()):
        with self.get_variables(source_dir, var_files) as var_files:
            graph = TerraformGraph(
                load_from_path(source_dir, vars_paths=var_files, allow_downloads=True),
                source_dir,
            )
            graph.build()
            log.debug("Loaded %d %s resources", len(graph), self.type)
            return graph

    def match_dir(self, source_dir):
        files = list(source_dir.glob("*.tf"))
        files += list(source_dir.glob("*.tf.json"))
        return files

    @contextlib.contextmanager
    def get_variables(self, source_dir, var_files, tf_vars=()):
        """handle all the ways to pass variables into terraform

        also perform various workarounds on tfparse's scanning to mirror terraform behavior.

        - pickup tf var files not in the root module
        - pickup auto.tfvars

        note TF_VAR_ environment variables are handled by tfparse.

        https://developer.hashicorp.com/terraform/language/values/variables#assigning-values-to-root-module-variables
        precedence
        https://www.ntweekly.com/2023/03/15/terraform-variables-precedence-and-order/
        """
        var_files = [Path(v) for v in var_files]
        resolved_files = []
        temp_files = []

        def write_file_content(content):
            fh = tempfile.NamedTemporaryFile(
                dir=source_dir, prefix="c7n-left-", suffix=".tfvars", mode="w+"
            )
            fh.write(content)
            fh.flush()
            temp_files.append(fh)
            resolved_files.append(Path(fh.name).relative_to(source_dir))

        # auto vars
        resolved_files.extend([f.relative_to(source_dir) for f in source_dir.rglob("*auto.tfvars")])
        resolved_files.extend(
            [f.relative_to(source_dir) for f in source_dir.rglob("*auto.tfvars.json")]
        )

        # see tf doc link above, these are also auto loaded.
        if (source_dir / "terraform.tfvars").exists():
            resolved_files.append(Path("terraform.tfvars"))
        if (source_dir / "terraform.tfvars.json").exists():
            resolved_files.append(Path("terraform.tfvars.json"))

        # move any files outside of module root into module as temp files.
        for v in var_files:
            if not v.is_absolute() and (source_dir / v).exists():
                resolved_files.append(v)
            elif v.is_absolute() and str(v).startswith(str(source_dir)):
                resolved_files.append(v.relative_to(source_dir))
            else:
                write_file_content(v.read_text())

        try:
            yield resolved_files
        finally:
            for fh in temp_files:
                fh.close()


@execution.register("terraform-source")
class TerraformSource(IACSourceMode):
    schema = type_schema("terraform-source")
