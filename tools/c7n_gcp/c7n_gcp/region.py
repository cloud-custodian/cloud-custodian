# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

from .provider import resources
from .query import TypeInfo
from c7n.cache import NullCache
from c7n.config import Config

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

    # allow tests to statically set to known regions
    _static_regions = None

    def __init__(self, ctx=None, data=None):
        self.ctx = ctx
        self.session_factory = None
        if ctx:
            self.config = ctx.options
        else:
            self.config = Config.empty()
        self.data = data or {}
        self._cache = NullCache(None)
        self.filters = ()
        self.actions = ()

        if self._static_regions:
            self.regions = set(self._static_regions)
            return
        with open(REGION_DATA_PATH) as fh:
            self.regions = set(json.load(fh))

    def get_permissions(self):
        return ()

    @classmethod
    def set_regions(cls, regions):
        # test helper
        if isinstance(regions, str):
            regions = (regions,)
        cls._static_regions = regions

    def resources(self, resource_ids=()):
        if resource_ids:
            return [{'name': r} for r in resource_ids if r in self.regions]
        if self.config.regions and 'all' in self.config.regions:
            return [{'name': r} for r in self.regions]

        if self.config.regions or self.config.region != 'us-east-1':
            regions = set(self.config.regions)
            if self.config.region:
                regions.add(self.config.region)
            if 'us-east-1' in regions:
                regions.remove('us-east-1')
            return [{'name': r} for r in regions if r in self.regions]

        # no self.config.regions
        if 'query' in self.data:
            return [
                {'name': q['name']}
                for q in self.data['query'] if q.get('name') in self.regions
            ]
        return [{'name': r} for r in self.regions]

    @classmethod
    def get_regions(cls):
        return list(cls().regions)

    def validate(self):
        pass
