# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import contextlib
import itertools
import json
import os
from pathlib import Path
import tempfile

import tfparse
import hcl2

from ...core import log
from .graph import TerraformGraph


class VariableResolver:
    """Handle variable value inputs.

    Handle all the ways to pass variables into terraform respecting
    precedence.

    This will also provide type based default variables for values
    that would otherwise not have a defined value, as any usage of them
    in a function otherwise resolves in an undefined/null attribute.

    This also perform various workarounds on tfparse's scanning to
    mirror terraform behavior.

    - pickup tf var files not in the root module
    - pickup auto.tfvars

    note TF_VAR_ environment variables are handled by tfparse, but we
    assess them to understand if a variable does not have a value set.

    References
     - https://developer.hashicorp.com/terraform/language/values/variables#variable-definition-precedence
     - https://www.ntweekly.com/2023/03/15/terraform-variables-precedence-and-order/
    """

    type_defaults = {
        "string": "",
        # open question if we should make this one for count usage
        "number": 0,
        # open question if we should default this to true for conditional inclusion
        "bool": False,
        "list": [],
        "tuple": [],
        "set": [],
        "map": {},
        "object": {},
    }

    def __init__(self, source_dir, var_files, reporter=None, stop_on_hcl_errors=False):
        self.source_dir = source_dir
        self.var_files = var_files
        self.resolved_files = {}
        self.temp_files = []
        self.reporter = reporter
        self.stop_on_hcl_errors = stop_on_hcl_errors

    def _write_file_content(self, content, suffix=".tfvars"):
        fh = tempfile.NamedTemporaryFile(
            dir=self.source_dir, prefix="c7n-left-", suffix=suffix, mode="w+", delete=False
        )
        fh.write(content)
        fh.flush()
        fh.close()
        self.temp_files.append(fh)
        return fh

    def report(self, var_type, var_map, path=None):
        if not self.reporter:
            return
        self.reporter.on_vars_discovered(var_type, var_map, path)

    @contextlib.contextmanager
    def get_variables(self):
        self.resolved_files["default"] = self.get_default_var_files()
        self.resolved_files["user"] = self.get_user_var_files()
        self.resolved_files["uninitialized"] = self.get_uninitialized_var_files()

        try:
            yield list(itertools.chain(*self.resolved_files.values()))
        finally:
            for t in self.temp_files:
                t.close()
                os.unlink(t.name)

    def get_uninitialized_var_files(self):
        # functions that operate on unknown values will typically result in
        # unknown / null results. to provide broad compatiblity we try to initialize
        # things with default values to facilitate attribute interpolation.
        var_map = self.get_env_variables()
        if var_map:
            self.report("environment", var_map)
        for type, f_set in self.resolved_files.items():
            for idx, f in enumerate(f_set):
                if str(f).endswith(".tfvars.json"):
                    f_vars = json.loads((self.source_dir / f).read_text())
                elif str(f).endswith(".tfvars"):
                    contents = (self.source_dir / f).read_text()
                    # the way the hcl2 library / parse is structured
                    # in golang/terraform it supports a file contents
                    # in either format, to preserve compatiblity, we
                    # check if its json, and if its not then load with
                    # hcl/terraform. we do json first as its fast to
                    # check and we can return back any hcl parse
                    # errors.
                    try:
                        f_vars = json.loads(contents)
                    except json.JSONDecodeError:
                        f_vars = hcl2.loads(contents)

                fpath = type == "user" and self.var_files[idx] or f
                if isinstance(fpath, Path):
                    fpath = fpath.name
                if f_vars:
                    self.report(type, f_vars, fpath)
                var_map.update(f_vars)

        uninitialized_vars = {}
        graph_data = tfparse.load_from_path(
            self.source_dir,
            allow_downloads=False,
            stop_on_hcl_error=self.stop_on_hcl_errors,
        )
        for _, variables in TerraformGraph(graph_data, self.source_dir).get_resources_by_type(
            "variable"
        ):
            for v in variables:
                if v.get("default"):
                    continue
                if not v["__tfmeta"]["path"].startswith("variable"):
                    continue
                if v["__tfmeta"]["label"] not in var_map:
                    uninitialized_vars[v["__tfmeta"]["label"]] = self.get_type_default(
                        v.get("type", "string") or "string"
                    )

        if not uninitialized_vars:
            return []

        log.debug("Using defaults for %d uninitialized variables", len(uninitialized_vars))
        self.report("uninitialized", uninitialized_vars)
        return [
            Path(
                self._write_file_content(json.dumps(uninitialized_vars), ".tfvars.json").name
            ).relative_to(self.source_dir.absolute())
        ]

    @classmethod
    def get_type_default(cls, vtype):
        if vtype in cls.type_defaults:
            return cls.type_defaults[vtype]
        elif " " in vtype:
            vtype, _ = vtype.split(' ', 1)
            return cls.type_defaults[vtype]
        return cls.type_defaults["string"]

    def get_env_variables(self):
        prefix = "TF_VAR_"
        return {k[len(prefix) :]: v for k, v in os.environ.items() if k.startswith(prefix)}

    def get_default_var_files(self):
        resolved_files = []
        # see tf link, these are also auto loaded.
        if (self.source_dir / "terraform.tfvars").exists():
            resolved_files.append(Path("terraform.tfvars"))
        if (self.source_dir / "terraform.tfvars.json").exists():
            resolved_files.append(Path("terraform.tfvars.json"))
        # auto vars
        resolved_files.extend(
            [f.relative_to(self.source_dir) for f in self.source_dir.glob("*auto.tfvars")]
        )
        resolved_files.extend(
            [f.relative_to(self.source_dir) for f in self.source_dir.glob("*auto.tfvars.json")]
        )
        return resolved_files

    def get_user_var_files(self):
        """return a set of tfvar files"""
        var_files = [Path(v) for v in self.var_files]
        resolved_files = []
        # move any files outside of module root into module as temp files.
        # work around for https://github.com/aquasecurity/trivy/issues/4006
        for v in var_files:
            if not v.is_absolute() and (self.source_dir / v).exists():
                resolved_files.append(v)
            elif v.is_absolute() and str(v).startswith(str(self.source_dir)):
                resolved_files.append(v.relative_to(self.source_dir))
            else:
                suffix = str(v).endswith(".tfvars.json") and ".tfvars.json" or ".tfvars"
                vfr = self._write_file_content(v.read_text(), suffix)
                resolved_files.append(Path(vfr.name).relative_to(self.source_dir.absolute()))
        return resolved_files
