# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import sys
import atheris


with atheris.instrument_imports():
    import json
    from c7n.exceptions import PolicyValidationError
    from c7n.resources.ebs import (
        SnapshotQueryParser as QueryParser
    )
    from c7n import utils


def fuzz_general(data):
    fdp = atheris.FuzzedDataProvider(data)
    schema_str = fdp.ConsumeUnicode(sys.maxsize)

    # Target parse_url_config
    utils.parse_url_config(schema_str)

    # Get a random dictionary
    try:
        schema = json.loads("{" + schema_str + "}")
    except Exception:
        return
    # Target date parsing
    utils.parse_date(schema_str)
    if isinstance(schema, dict):
        utils.camelResource(schema, True)
    # Target query parse
    try:
        QueryParser.parse([schema])
    except PolicyValidationError:
        None


def main():
    atheris.Setup(sys.argv, fuzz_general)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
