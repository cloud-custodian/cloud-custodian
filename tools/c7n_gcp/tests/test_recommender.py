# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
import re
from urllib.request import urlopen

import pytest

from c7n.testing import functional
from c7n_gcp.filters.recommender import get_recommender_data


RECOMMENDERS_URL = 'https://docs.cloud.google.com/recommender/docs/recommenders.md.txt'


def check_recommender_ids(catalog, document):
    # Keep identifiers separate when one table cell documents multiple recommenders.
    documented = set(re.findall(r'\bgoogle(?:\.[A-Za-z0-9_]+)+', document))
    assert documented, 'No recommender IDs found in the API documentation'
    mismatched = sorted(key for key, value in catalog.items() if key != value['id'])
    assert not mismatched, f'Recommender catalog keys do not match their IDs: {mismatched}'
    unknown = sorted(set(catalog).difference(documented))
    assert not unknown, f'Recommender IDs missing from the API documentation: {unknown}'


@functional
@pytest.mark.skipif(
    os.environ.get('C7N_RECOMMENDER_DOCS') != 'yes',
    reason='Set C7N_RECOMMENDER_DOCS=yes to check Google documentation')
def test_recommender_catalog():
    # An explicit live check; ordinary replay suites must not depend on the docs site.
    with urlopen(RECOMMENDERS_URL, timeout=30) as response:
        document = response.read().decode('utf-8')
    check_recommender_ids(get_recommender_data(), document)


def test_documented_recommender_ids():
    ids = ('google.run.service.IdentityRecommender', 'google.run.service.SecurityRecommender')
    catalog = {rec_id: {'id': rec_id} for rec_id in ids}
    # New upstream entries need not all be supported by Custodian.
    document = (
        '| Security | Cloud Run | `' + '\n'.join(ids) + '` | Description |\n'
        '| Cost | Disk | `google.compute.disk.IdleResourceRecommender` | Description |'
    )
    check_recommender_ids(catalog, document)


@pytest.mark.parametrize('rec_id', [
    'google.compute.commitment.UsageCommitmentRecommender'
    'google.cloudbilling.commitment.SpendBasedCommitmentRecommender',
    'google.run.service.IdentityRecommendergoogle.run.service.SecurityRecommender',
    'google.compute.disk.IdleResourceRecommenderTypo',
])
def test_undocumented_recommender_id(rec_id):
    document = '''
    `google.compute.commitment.UsageCommitmentRecommender
    google.cloudbilling.commitment.SpendBasedCommitmentRecommender`
    `google.run.service.IdentityRecommender
    google.run.service.SecurityRecommender`
    `google.compute.disk.IdleResourceRecommender`
    '''
    with pytest.raises(AssertionError, match=re.escape(rec_id)):
        check_recommender_ids({rec_id: {'id': rec_id}}, document)


def test_recommender_key_must_match_id():
    with pytest.raises(AssertionError, match='keys do not match'):
        check_recommender_ids(
            {'google.run.service.SecurityRecommender': {
                'id': 'google.run.service.IdentityRecommender'}},
            'google.run.service.SecurityRecommender google.run.service.IdentityRecommender')


@pytest.mark.parametrize('document', ['', '<html>Site Unavailable</html>'])
def test_missing_documented_ids(document):
    with pytest.raises(AssertionError, match='No recommender IDs found'):
        check_recommender_ids({}, document)


def test_cloud_run_security_recommender(test):
    policy = test.load_policy({
        'name': 'cloud-run-security',
        'resource': 'gcp.cloud-run-service',
        'filters': [{
            'type': 'recommend',
            'id': 'google.run.service.SecurityRecommender',
        }],
    }, validate=True)
    assert policy.resource_manager.filters[0].get_permissions() == [
        'recommender.runServiceSecurityRecommendations.get',
        'recommender.runServiceSecurityRecommendations.list',
    ]
