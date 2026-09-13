set working-directory := ".."

@_default:
    just --list data

# Regenerate all data sets: terraform, AWS, and GCP.
@update:
    #!/usr/bin/env bash
    set -euo pipefail

    # terraform data sets
    (cd tools/c7n_left/scripts && uv run python get_taggable.py \
        --module-path taggable_providers/latest \
        --module-path taggable_providers/azurerm-previous \
        --output ../c7n_left/data/taggable.json)

    # aws data sets
    uv run python tools/dev/data_cftypedb.py -f tests/data/cfn-types.json
    uv run python tools/dev/data_updatearnref.py > tests/data/arn-types.json
    uv run python tools/dev/data_iamdb.py -f tests/data/iam-actions.json
    uv run python tools/dev/data_awspartitions.py > c7n/data/aws_region_partition_map.json

    # gcp data sets
    uv run python tools/dev/data_gcpiamdb.py -f tools/c7n_gcp/tests/data/iam-permissions.json
    uv run python tools/dev/data_gcpregion.py -f tools/c7n_gcp/c7n_gcp/regions.json
