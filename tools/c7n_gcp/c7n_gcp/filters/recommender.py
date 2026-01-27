# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
GCP Recommender filters
"""
import json
from pathlib import Path

import jmespath

from c7n.exceptions import PolicyValidationError
from c7n.filters.core import Filter
from c7n.utils import local_session, type_schema

from c7n_gcp.provider import resources as gcp_resources


RECOMMENDER_DATA_PATH = Path(__file__).parent / "recommender.json"
_RECOMMENDER_DATA = None


def get_recommender_data():
    global _RECOMMENDER_DATA
    if _RECOMMENDER_DATA is None:
        with open(RECOMMENDER_DATA_PATH) as fh:
            _RECOMMENDER_DATA = json.load(fh)
    return _RECOMMENDER_DATA


class RecommenderFilter(Filter):
    """Use GCP Resource Recommendations to filter resources

    for a complete list and applicable resource types see
    https://cloud.google.com/recommender/docs/recommenders

    ie. find idle compute disks to snapshot and delete.

    :example:

    .. code-block:: yaml

      policies:
        - name: gcp-unused-disk
          resource: gcp.disk
          filters:
           - type: recommend
             id: google.compute.disk.IdleResourceRecommender
          actions:
           - snapshot
           - delete

    """
    schema = type_schema(
        "recommend",
        id={"type": "string"},
        # state={'enum': ['ACTIVE', 'CLAIMED', 'SUCCEEDED', 'FAILED', 'DISMISSED']}
        # sub_type={'enum': 'string'}
        required=("id",),
    )
    schema_alias = True
    annotation_key = 'c7n:recommend'

    def get_permissions(self):
        rec_id = self.data.get("id")
        if not rec_id:
            return []
        prefix = get_recommender_data().get(rec_id, {}).get("permission_prefix")
        if not prefix:
            return []
        return [prefix + ".get", prefix + ".list"]

    def validate(self):
        rtype = "gcp.%s" % self.manager.type
        rec_id = self.data["id"]
        all_recs = get_recommender_data()

        if rec_id not in all_recs or all_recs[rec_id].get('resource', '') != rtype:
            valid_ids = {r["id"] for r in all_recs.values() if r.get("resource") == rtype}
            raise PolicyValidationError(
                f"recommendation id:{rec_id} is not valid for {rtype}, valid: {valid_ids}"
            )

        self.rec_info = all_recs[rec_id]

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        recommendations = self.get_recommendations(session, resources)
        return self.match_resources(recommendations, resources)

    def get_recommendations(self, session, resources):
        client = session.client(
            "recommender", "v1", "projects.locations.recommenders.recommendations"
        )
        project = session.get_default_project()
        regions = self.get_regions(resources)

        recommends = []
        for r in regions:
            parent = (
                f"projects/{project}/locations/{r}/recommenders/{self.rec_info['id']}"
            )
            for page in client.execute_paged_query("list", {"parent": parent}):
                recommends.extend(page.get('recommendations', []))
        return recommends

    def match_resources(self, recommends, resources):
        results = []
        rec_query = jmespath.compile('content.operationGroups[].operations[].resource')
        for r in recommends:
            rids = set(rec_query.search(r))
            for rid in list(rids):
                # some resource operations are about creating new resources, ie snapshot disk
                # before delete, remove those to focus on extant resources.
                if "$" in rid:
                    rids.remove(rid)
            matched = list(self.match_ids(rids, resources))
            for m in matched:
                m.setdefault(self.annotation_key, []).append(r)
            results.extend(matched)
        return results

    def match_ids(self, rids, resources):
        rids = [r.split("/", 3)[-1] for r in rids]
        for r in resources:
            for rid in rids:
                if rid in r["name"] or rid in r["selfLink"]:
                    yield r

    def get_regions(self, resources):
        locator = self.manager.resource_type._get_location
        return list(set([locator(r) for r in resources]))

    @classmethod
    def register_resources(klass, registry, resource_class):
        data = get_recommender_data()
        rtype = "gcp.%s" % resource_class.type
        for rec in data.values():
            if rec.get("resource") == rtype:
                resource_class.filter_registry.register("recommend", klass)


gcp_resources.subscribe(RecommenderFilter.register_resources)
