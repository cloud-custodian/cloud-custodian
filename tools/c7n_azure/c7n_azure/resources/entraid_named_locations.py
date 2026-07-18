# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n.filters import Filter, ValueFilter
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.graph_utils import GraphResourceManager, GraphTypeInfo, GraphSource

log = logging.getLogger('custodian.azure.entraid.named_locations')


@resources.register('entraid-named-location')
class EntraIDNamedLocation(GraphResourceManager):
    """EntraID Named Location resource for managing locations in Conditional Access policies.

    Named locations are trusted IP ranges or countries/regions that can be used in
    Conditional Access policies. This resource type supports querying and managing
    both IP-based and country/region-based named locations.

    Permissions:
    - Policy.Read.All for reading named locations
    - Policy.ReadWrite.ConditionalAccess for modifying named locations

    :example:

    Find all IP-based named locations:

    .. code-block:: yaml

        policies:
          - name: ip-named-locations
            resource: azure.entraid-named-location
            filters:
              - type: location-type
                location-type: ipNamedLocation

    :example:

    Find named locations containing specific IP ranges:

    .. code-block:: yaml

        policies:
          - name: specific-ip-ranges
            resource: azure.entraid-named-location
            filters:
              - type: location-type
                location-type: ipNamedLocation
              - type: value
                key: ipRanges[*].cidrAddress
                op: contains
                value: "10.0.0.0/8"
    """

    def __init__(self, ctx, data):
        super().__init__(ctx, data)
        self.source = GraphSource(self)

    class resource_type(GraphTypeInfo):
        doc_groups = ['EntraID', 'Identity']
        enum_spec = ('identity/conditionalAccess/namedLocations', 'list', None)
        detail_spec = ('identity/conditionalAccess/namedLocations', 'get', 'id')
        id = 'id'
        name = 'displayName'
        date = 'createdDateTime'
        default_report_fields = (
            'displayName',
            'createdDateTime',
            'modifiedDateTime',
            'id'
        )
        permissions = ('Policy.Read.All',)

    def get_graph_resources(self):
        """Get named locations from Microsoft Graph API."""
        try:
            response = self.make_graph_request('identity/conditionalAccess/namedLocations')
            resources = response.get('value', [])

            log.debug(f"Retrieved {len(resources)} named locations from Graph API")

            # Add computed fields
            resources = self.augment(resources)

            log.debug(f"Returning {len(resources)} named locations after augmentation")
            return resources
        except Exception as e:
            log.error(f"Error retrieving EntraID named locations: {e}")
            if "Insufficient privileges" in str(e) or "403" in str(e):
                log.error(
                    "Insufficient privileges to read named locations. "
                    "Required permission: Policy.Read.All"
                )
            return []

    def augment(self, resources):
        """Augment named location resources with additional fields."""
        try:
            for resource in resources:
                # Add computed fields based on location type
                odata_type = resource.get('@odata.type', '')
                resource['c7n:IsIPLocation'] = (
                    '#microsoft.graph.ipNamedLocation' in odata_type
                )
                resource['c7n:IsCountryLocation'] = (
                    '#microsoft.graph.countryNamedLocation' in odata_type
                )

                # Add total IP ranges count for IP-based locations
                if resource['c7n:IsIPLocation']:
                    ip_ranges = resource.get('ipRanges', [])
                    resource['c7n:IPRangesCount'] = len(ip_ranges)

                # Add total countries count for country-based locations
                if resource['c7n:IsCountryLocation']:
                    countries = resource.get('countriesAndRegions', [])
                    resource['c7n:CountriesCount'] = len(countries)

        except Exception as e:
            log.warning(f"Failed to augment EntraID named locations: {e}")

        return resources


@EntraIDNamedLocation.filter_registry.register('location-type')
class LocationTypeFilter(Filter):
    """Filter named locations by type (IP-based or country-based).

    :example:

    Find all country-based named locations:

    .. code-block:: yaml

        policies:
          - name: country-named-locations
            resource: azure.entraid-named-location
            filters:
              - type: location-type
                location-type: countryNamedLocation
    """

    schema = type_schema('location-type',
                        **{
                            'location-type': {
                                'type': 'string',
                                'enum': ['ipNamedLocation', 'countryNamedLocation']
                            }
                        })

    def process(self, resources, event=None):
        location_type = self.data.get('location-type', 'ipNamedLocation')

        filtered = []
        for resource in resources:
            if '@odata.type' in resource:
                if location_type == 'ipNamedLocation' and resource['c7n:IsIPLocation']:
                    filtered.append(resource)
                elif location_type == 'countryNamedLocation' and resource['c7n:IsCountryLocation']:
                    filtered.append(resource)

        return filtered


@EntraIDNamedLocation.filter_registry.register('ip-range-count')
class IPRangeCountFilter(ValueFilter):
    """Filter IP-based named locations by number of IP ranges.

    This filter uses the c7n:IPRangesCount annotation added during resource augmentation.
    It supports all standard ValueFilter operators (greater-than, less-than, equal, etc.).

    :example:

    Find named locations with more than 10 IP ranges:

    .. code-block:: yaml

        policies:
          - name: large-ip-locations
            resource: azure.entraid-named-location
            filters:
              - type: location-type
                location-type: ipNamedLocation
              - type: ip-range-count
                value: 10
                op: greater-than
    """

    schema = type_schema('ip-range-count', rinherit=ValueFilter.schema)
    schema_alias = True

    def __init__(self, data, manager=None):
        # Set the key to the annotation that contains the IP ranges count
        data['key'] = 'c7n:IPRangesCount'
        super(IPRangeCountFilter, self).__init__(data, manager)

    def process(self, resources, event=None):
        # Filter out non-IP locations before applying the value filter
        ip_locations = [r for r in resources if r.get('c7n:IsIPLocation')]
        return super(IPRangeCountFilter, self).process(ip_locations, event)


@EntraIDNamedLocation.filter_registry.register('countries-count')
class CountriesCountFilter(ValueFilter):
    """Filter country-based named locations by number of countries/regions.

    This filter uses the c7n:CountriesCount annotation added during resource augmentation.
    It supports all standard ValueFilter operators (greater-than, less-than, equal, etc.).

    :example:

    Find named locations with more than 5 countries:

    .. code-block:: yaml

        policies:
          - name: multi-country-locations
            resource: azure.entraid-named-location
            filters:
              - type: location-type
                location-type: countryNamedLocation
              - type: countries-count
                value: 5
                op: greater-than
    """

    schema = type_schema('countries-count', rinherit=ValueFilter.schema)
    schema_alias = True

    def __init__(self, data, manager=None):
        # Set the key to the annotation that contains the countries count
        data['key'] = 'c7n:CountriesCount'
        super(CountriesCountFilter, self).__init__(data, manager)

    def process(self, resources, event=None):
        # Filter out non-country locations before applying the value filter
        country_locations = [r for r in resources if r.get('c7n:IsCountryLocation')]
        return super(CountriesCountFilter, self).process(country_locations, event)
