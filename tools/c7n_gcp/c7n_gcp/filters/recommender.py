# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
GCP Recommender filters
"""
import json
from pathlib import Path

from c7n.filters.core import Filter
from c7n.utils import lcoal_session, type_schema
from c7n.region import Region

RECOMMENDER_DATA_PATH = Path(__file__).parent / "recommender.json"
_RECOMMENDER_DATA = None


def get_recommender_data():
    global _RECOMMENDER_DATA
    if _RECOMMENDER_DATA is None:
        with open(RECOMMENDER_DATA_PATH) as fh:
            _RECOMMENDER_DATA = json.load(fh)


class RecommenderFilter(Filter):

    schema = type_schema(
        'recommender',
        id={'type': 'string'},
        # state={'enum': ['ACTIVE', 'CLAIMED', 'SUCCEEDED', 'FAILED', 'DISMISSED']}
        # sub_type={'enum': 'string'}
        required=('id',)
    )

    def get_permissions(self):
        rec_id = self.data.get('id')
        if not rec_id:
            return []
        prefix = get_recommender_data().get(rec_id, {}).get('permissions_prefix')
        if not prefix:
            return []
        return [prefix + '.get', prefix + '.list']

    def validate(self):
        rtype = "gcp.%s" % self.manager.type
        rec_id = self.data['id']
        all_recs = get_recommender_data()

        if rec_id not in all_recs or all_recs[rec_id] != rtype:
            valid_ids = {r['id'] for r in all_recs if r.get('resource') == rtype}            
            raise PolicyValidationError(f"recommendation id:{rec_id} is not valid for {rtype}, valid: {valid_ids}")

        self.rec_info = all_recs[rec_id]

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        recommendations = self.get_recommendations(session, resources)
        return self.match_resources(recommendations, resources)

    def get_recommendations(self, session, resources):
        client = session.client('recommender', 'v1', 'projects.locations.recommenders.recommendations')
        project = session.get_default_project()
        regions = self.get_regions(resources)

        recommends = []
        for r in regions:
            parent = f"projects/{project}/locations/{r}/recommenders/{self.rec_info['id']}"
            for page in client.execute_paged_query("list", {"parent": parent}):
                recommends.extend(page)
        return recommends

    def match_resources(self, resources, recommends):
        results = []
        rec_query = jmespath.compile('content.operationsGroups[].operations[].resource')
        for r in recommends:
            rids = rec_query.search(r)
            for rid in list(rids):
                if '$' in rid:
                    rids.remove(rid)
            matched = self.match_ids(rids, resources)
            for m in matched:
                m.setdefault(self.annotation, []).append(r)
            results.extend(matched)
        return results

    def match_ids(self, rids, resources):
        rids = [r.split('/', 3)[-1] for r in rids]
        for r in resources:
            for rid in rids:
                if rid in r['name'] or rid in r['selfLink']:
                    yield r

    def get_regions(self, resources):
        return Region.get_regions()

    @classmethod
    def register_resources(klass, registry, resource_class):
        data = get_recommender_data()
        rtype = "gcp.%s" % resource_class.type
        for rec in data.values():
            if rec.get('resource') == rtype:
                resource_class.filter_registry.register('recommends', klass)
        

        
        
        
        
        
        
