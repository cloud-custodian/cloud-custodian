# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

from .provider import resources
from .query import TypeInfo


REGION_DATA_PATH = Path(__file__).parent / "regions.json"


@resources.register('region')
class Region:

    class resource_type(TypeInfo):

        name = id = 'name'
        scope = 'global'
        default_report_fields = ['name']
        service = 'regions'

    filter_registry = {}
    action_registry = {}

    def __init__(self, ctx=None, data=()):
        self.ctx = ctx
        self.data = data
        with open(REGION_DATA_PATH) as fh:
            self.regions = json.load(fh)

    def get_permissions(self):
        return ()

    def resources(self, resource_ids=()):
        if resource_ids:
            return [{'name': r} for r in self.regions if r in resource_ids]
        elif 'query' in self.data:
            qregions = {q['name'] for q in self.data['query']}
            return [{'name': r} for r in self.regions if r in qregions]
        else:
            return [{'name': r} for r in self.regions]

    @classmethod
    def get_regions(cls):
        return list(cls().regions)
