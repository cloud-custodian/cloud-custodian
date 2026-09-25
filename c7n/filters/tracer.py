"""Filter match tracing - second-pass per-resource trace of a filter tree.

Normal c7n filter evaluation runs first (unchanged). After matched resources
are identified, call attach_traces(filters, resources) to walk the filter tree
per-resource and attach a detailed match trace as ``c7n:MatchTrace`` on each
resource dict.
"""

MATCH_TRACE_KEY = "c7n:MatchTrace"
MATCH_TRACE_SUMMARY_KEY = "c7n:MatchTraceSummary"
MATCH_TRACE_SLIM_KEY = "c7n:MatchTraceSlim"

_MARK = {True: "⊤", False: "⊥", None: "?"}  # logical true / false / unknown


def trace_filter(f, resource):
    """Recursively trace a single filter against one resource.

    Returns a dict describing the node's type, matched status, and -- for
    composite filters -- the children's individual trace nodes.

    `matched` is:
    - True / False when the filter was successfully evaluated per-resource
    - None when the filter cannot be evaluated per-resource (bulk-only)
    """
    from c7n.filters.core import Or, And, Not, ValueFilter
    from c7n.filters.related import RelatedResourceFilter

    if isinstance(f, Not):
        children = [trace_filter(c, resource) for c in f.filters]
        # NOT uses implicit-AND semantics: the whole NOT block matches when
        # the inner AND of its children is False (i.e. at least one child is
        # False). We compute the inner AND across non-None children.
        truthy = [c["matched"] for c in children if c["matched"] is not None]
        inner_matched = all(truthy) if truthy else True
        matched = not inner_matched
        return {"type": "not", "matched": matched, "children": children}

    if isinstance(f, Or):
        children = [trace_filter(c, resource) for c in f.filters]
        matched = any(c["matched"] for c in children if c["matched"] is not None)
        return {"type": "or", "matched": matched, "children": children}

    if isinstance(f, And):
        children = [trace_filter(c, resource) for c in f.filters]
        truthy = [c["matched"] for c in children if c["matched"] is not None]
        matched = all(truthy) if truthy else True
        return {"type": "and", "matched": matched, "children": children}

    if isinstance(f, RelatedResourceFilter):
        # RelatedResourceFilter's real per-resource logic lives in
        # process_resource(resource, related), not match() -- match() only
        # tests a single related object, not the or/and-across-related-ids
        # semantics process_resource applies. Fetch just this resource's
        # related objects and defer to the same method process() uses.
        related = f.get_related([resource])
        matched = f.process_resource(resource, related)
        return {
            "type": "value",
            "key": f.k,
            "op": f.op or "eq",
            "expected": f.v,
            "related_ids": sorted(related),
            "matched": matched,
        }

    if isinstance(f, ValueFilter):
        # Calling match() is idempotent -- content_initialized flag ensures
        # f.k/op/v are set on first call and frozen thereafter.
        matched = f.match(resource)
        # Retrieve the actual resource value using the already-initialised key.
        if f.k is not None:
            actual = f.get_resource_value(f.k, resource)
        else:
            actual = None
        return {
            "type": "value",
            "key": f.k,
            "op": f.op or "eq",
            "expected": f.v,
            "actual": actual,
            "value_type": getattr(f, "vtype", None),  # may be None for simple equality checks
            "matched": matched,
        }

    # Unknown / custom filter - attempt per-resource call.
    try:
        result = f(resource)
        return {"type": type(f).__name__, "matched": result}
    except Exception:
        # Bulk-only filters (e.g. resource_count) cannot be evaluated per
        # resource. Use matched=None so callers can distinguish "didn't
        # match" from "couldn't evaluate".
        return {
            "type": type(f).__name__,
            "matched": None,
            "reason": "non-per-resource filter",
        }


def format_trace(trace):
    """Render a trace_filter() node as a single human-readable expression.

    Composite nodes render as ``MARK TYPE(child, child, ...)``; value nodes
    render as ``MARK key op expected -> actual``. MARK is one of ✓ / ✗ / ?
    for matched True / False / None.
    """
    mark = _MARK[trace["matched"]]
    node_type = trace["type"]

    if node_type in ("and", "or", "not"):
        children = ", ".join(format_trace(c) for c in trace["children"])
        return f"{mark} {node_type.upper()}({children})"

    if node_type == "value":
        if "related_ids" in trace:
            return (
                f"{mark} {trace['key']} {trace['op']} {trace['expected']!r} "
                f"related:{trace['related_ids']!r}"
            )
        return f"{mark} {trace['key']} {trace['op']} {trace['expected']!r} -> {trace['actual']!r}"

    return f"{mark} {node_type}"


def slim_trace(trace):
    """Prune a trace_filter() node down to only the children that decided
    its result -- the branches that actually caused the resource to appear
    (or not) in the policy, dropping the ones that didn't matter.

    - or: if matched, keep only the matching children (an or needs just one);
      if not matched, every child failed and all are kept.
    - and / not: both reduce to an inner AND across children. If that inner
      AND is True, every child had to pass, so all are kept; if it's False,
      only the failing child(ren) are kept (the ones that broke it).
    - Children with matched=None (bulk-only, couldn't be evaluated) are
      always kept, since we can't rule out their contribution.
    - Leaf (value) nodes are returned as-is.
    """
    node_type = trace["type"]
    if node_type not in ("and", "or", "not"):
        return dict(trace)

    children = trace["children"]
    if node_type == "or":
        relevant = children if not trace["matched"] else [
            c for c in children if c["matched"] is not False]
    else:
        inner_and_true = trace["matched"] if node_type == "and" else not trace["matched"]
        relevant = children if inner_and_true else [
            c for c in children if c["matched"] is not True]

    result = dict(trace)
    result["children"] = [slim_trace(c) for c in relevant]
    return result


def attach_traces(filters, resources):
    """Attach a match trace to each resource in *resources*.

    For each resource a top-level list of trace nodes (one per top-level
    filter) is computed by calling trace_filter on every filter and stored
    under the ``c7n:MatchTrace`` key directly on the resource dict. A
    condensed, human-readable rendering of the same traces (one string per
    top-level filter, via format_trace) is stored under
    ``c7n:MatchTraceSummary``. A pruned version of the traces containing only
    the branches that decided the result (via slim_trace) is stored under
    ``c7n:MatchTraceSlim``.

    This function has no return value; it mutates the resource dicts in place.
    """
    for resource in resources:
        traces = [trace_filter(f, resource) for f in filters]
        resource[MATCH_TRACE_KEY] = traces
        resource[MATCH_TRACE_SUMMARY_KEY] = [format_trace(t) for t in traces]
        resource[MATCH_TRACE_SLIM_KEY] = [slim_trace(t) for t in traces]
