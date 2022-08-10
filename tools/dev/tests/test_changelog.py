# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest


pytest.importorskip('pygit2')

schema_diff = Path(__file__).parent.parent / "changelog.py"
with open(schema_diff, encoding='utf-8') as f:
    exec(f.read())


@pytest.mark.parametrize('provider, resource, category, element, expected', [
    ('aws', 'firehose', 'filters', 'kms-key',
     '[`kms-key`](https://cloudcustodian.io/docs/aws/resources/firehose.html#aws-firehose-filters-kms-key)'),  # noqa
    (None, 'gcp.pubsub-topic', 'actions', 'delete',
     '[`delete`](https://cloudcustodian.io/docs/gcp/resources/pubsub-topic.html#gcp-pubsub-topic-actions-delete)'),  # noqa
    ('aws', 'elasticsearch', None, None,
     '[`aws.elasticsearch`](https://cloudcustodian.io/docs/aws/resources/elasticsearch.html)'),
    ('aws', None, 'filters', 'reduce',
     '[`reduce`](https://cloudcustodian.io/docs/aws/resources/aws-common-filters.html#aws-common-filters-reduce)'),  # noqa
])
def test_link(provider, resource, category, element, expected):
    got = link(  # noqa
        provider=provider,
        resource=resource,
        category=category,
        element=element,
    )
    assert got == expected


def test_schema_diff():
    data_dir = Path(__file__).parent / "data"
    with open(data_dir / "schema-old.json") as f:
        schema_old = json.load(f)
    with open(data_dir / "schema-new.json") as f:
        schema_new = json.load(f)
    with open(data_dir / "diff.md", encoding='utf-8') as f:
        expected = f.read()

    result = schema_diff(schema_old, schema_new)  # noqa
    assert result == expected
