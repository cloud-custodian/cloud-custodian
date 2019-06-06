.. _azure_filters:

Generic Filters
===============

These filters can be applied to all policies for multiple resources.

Firewall Rules Filter
---------------------

- ``firewall-rules`` Filter based on firewall rules. Rules can be specified as x.x.x.x-y.y.y.y or x.x.x.x or x.x.x.x/y.
  - `include`: the list of IP ranges or CIDR that firewall rules must include. The list must be a subset of the exact rules as is, the ranges will not be combined.
  - `equal`: the list of IP ranges or CIDR that firewall rules must match exactly.

