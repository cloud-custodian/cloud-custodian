# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import yaml
from yaml.error import MarkedYAMLError

from c7n.commands import DuplicateKeyCheckLoader
from c7n.exceptions import PolicyValidationError
from c7n.resources import load_resources
from c7n.schema import generate as schema_generate
from c7n.schema import validate as schema_validate
from c7n.structure import StructureParser

from .entry import initialize_iac


def validate_files(policy_files):
    resource_types = ("terraform._",)
    initialize_iac()
    load_resources(resource_types)
    schema = schema_generate(resource_types)

    parser = StructureParser()
    all_errors = {}

    for policy_file in policy_files:

        with open(policy_file) as fh:
            # Check valid file format
            try:
                data = yaml.load(fh, Loader=DuplicateKeyCheckLoader)  # nosec nosemgrep
            except MarkedYAMLError as e:
                all_errors[policy_file] = (e,)
                continue

            # Sanity check top level keys, this allows us to give a
            # better error message then jsonschema
            try:
                parser.validate(data)
            except PolicyValidationError as e:
                all_errors[policy_file] = (e,)
                continue

            # Check json schema validation
            errors = schema_validate(data, schema)
            if errors:
                all_errors[policy_file] = [errors[0]]
    return all_errors
