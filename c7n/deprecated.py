# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

"""Deprecations of policy elements.

Initial thinking around the deprecation is identifying changes in filters and
actions. These are likely to be the most common aspects:
 * renaming a field
 * making an optional field required
 * removing a field

Examples:
 - renaming a filter itself
c7n_azure/resources/key_vault
@KeyVault.filter_registry.register('whitelist')
- filter 'whitelist' has been deprecated (replaced by 'allow')

- mark -> tag
- unmark, untag -> remove-tag


 - renaming filter attributes
c7n/filters/iamaccess
   schema = type_schema(
       'cross-account',
       ...
       whitelist_from={'$ref': '#/definitions/filters_common/value_from'},
       whitelist={'type': 'array', 'items': {'type': 'string'}},
       ...)
- filter field 'whitelist' has been deprecated (replaced by 'allow')


c7n/tags.py
 - optional attributes becoming required, in this case one of 'days' or 'hours'
 - optional action fields deprecated (one of 'days' or 'hours' must be specified)
 - optional action field 'tag' deprecated (must be specified)

"""

# Treat deprecation warnings as errors.
STRICT = "strict"
# Skip checking for deprecations
SKIP = "skip"


def alias(name, removed_after=None, link=None):
    """A filter or action alias is deprecated."""
    return DeprecatedAlias(name, removed_after, link)


def action(replacement, removed_after=None, link=None):
    """The action has been superseded by another action."""
    return DeprecatedElement('action', replacement, removed_after, link)


def filter(replacement, removed_after=None, link=None):
    """The filter has been superseded by another filter."""
    return DeprecatedElement('filter', replacement, removed_after, link)


def field(name, replacement, removed_after=None, link=None):
    """The field has been renamed to something else."""
    return DeprecatedField(name, replacement, removed_after, link)


def optional_field(name, removed_after=None, link=None):
    """The field must now be specified."""
    return DeprecatedOptionality([name], removed_after, link)


def optional_fields(names, removed_after=None, link=None):
    """One of the field names must now be specified."""
    return DeprecatedOptionality(names, removed_after, link)


class Deprecation:
    """Base class for different deprecation types."""
    _id = 0

    def __init__(self, removed_after, link):
        """All deprecations can have a removal date, and a link to docs.

        Both of these fields are optional.

        removed_after if specified must be a string representing an ISO8601 date.
        """
        self.removed_after = removed_after
        self.link = link
        self.id = Deprecation._id
        Deprecation._id += 1

    @property
    def remove_text(self):
        if self.removed_after is None:
            return ""
        return f"Will be removed after {self.removed_after}"

    def check(self, data):
        return True


class DeprecatedAlias(Deprecation):
    def __init__(self, name, removed_after=None, link=None):
        super().__init__(removed_after, link)
        self.name = name

    def __str__(self):
        return f"alias '{self.name}' has been deprecated"

    def check(self, data):
        return data.get("type") == self.name


class DeprecatedField(Deprecation):
    def __init__(self, name, replacement, removed_after=None, link=None):
        super().__init__(removed_after, link)
        self.name = name
        self.replacement = replacement

    def __str__(self):
        # filter or action prefix added by Filter and Action classes
        name, replacement = self.name, self.replacement
        # If the replacement is a single word we surround it with quotes,
        # otherwise we just use the replacement as is.
        if ' ' not in replacement:
            replacement = "'" + replacement + "'"
        return f"field '{name}' has been deprecated (replaced by {replacement})"

    def check(self, data):
        if self.name in data:
            return True
        return False


class DeprecatedElement(Deprecation):
    def __init__(self, name, replacement, removed_after=None, link=None):
        super().__init__(removed_after, link)
        self.name = name
        self.replacement = replacement

    def __str__(self):
        # filter or action prefix added by Filter and Action classes
        name, replacement = self.name, self.replacement
        return f"{name} has been deprecated ({replacement})"

    def check(self, data):
        return True


class DeprecatedOptionality(Deprecation):
    def __init__(self, fields, removed_after=None, link=None):
        super().__init__(removed_after, link)
        self.fields = fields

    def check(self, data):
        # check to see that they haven't specified the value
        return all([key not in data for key in self.fields])

    def __str__(self):
        if len(self.fields) > 1:
            quoted = [f"'{field}'" for field in self.fields]
            names = ' or '.join(quoted)
            return f"optional fields deprecated (one of {names} must be specified)"

        field = self.fields[0]
        return f"optional field '{field}' deprecated (must be specified)"

    @property
    def remove_text(self):
        if self.removed_after is None:
            return ""
        return f"Will become an error after {self.removed_after}"


class Context:
    """Adds extra context to a deprecation."""
    def __init__(self, context, deprecation):
        self.context = context
        self.deprecation = deprecation

    def __str__(self):
        return f"{self.context} {self.deprecation}"

    @property
    def id(self):
        return self.deprecation.id

    @property
    def link(self):
        return self.deprecation.link

    @property
    def remove_text(self):
        return self.deprecation.remove_text


def check_deprecations(source, context=None, data=None):
    if data is None:
        data = getattr(source, 'data', {})
    deprecations = []
    for d in getattr(source, 'deprecations', ()):
        if d.check(data):
            if context is not None:
                d = Context(context, d)
            deprecations.append(d)
    return deprecations


def report(policy):
    """Generate the deprecation report for the policy."""
    policy_fields = policy.get_deprecations()
    conditions = policy.conditions.get_deprecations()
    mode = policy.get_execution_mode().get_deprecations()
    filters = []
    actions = []
    rm = policy.resource_manager
    resource = rm.get_deprecations()
    for f in rm.filters:
        filters.extend(f.get_deprecations())
    for a in rm.actions:
        actions.extend(a.get_deprecations())
    return Report(policy.name, policy_fields, conditions,
                  mode, resource, filters, actions)


class Report:
    """A deprecation report is generated per policy."""

    def __init__(self, policy_name, policy_fields=(), conditions=(), mode=(),
                 resource=(), filters=(), actions=()):
        self.policy_name = policy_name
        self.policy_fields = policy_fields
        self.conditions = conditions
        self.mode = mode
        self.resource = resource
        self.filters = filters
        self.actions = actions

    def __bool__(self):
        # Start by checking the most likely things.
        if len(self.filters) > 0:
            return True
        if len(self.actions) > 0:
            return True
        if len(self.policy_fields) > 0:
            return True
        if len(self.conditions) > 0:
            return True
        if len(self.resource) > 0:
            return True
        if len(self.mode) > 0:
            return True
        return False

    def format(self, source_locator=None, footnotes=None):
        """Format the report for output.

        If a source locator is specified, it is used to provide file and line number
        information for the policy.
        """
        location = ""
        if source_locator is not None:
            file_and_line = source_locator.find(self.policy_name)
            if file_and_line:
                location = f" ({file_and_line})"
        lines = [f"policy '{self.policy_name}'{location}"]
        lines.extend(self.section('attributes', self.policy_fields, footnotes))
        lines.extend(self.section('condition', self.conditions, footnotes))
        lines.extend(self.section('mode', self.mode, footnotes))
        lines.extend(self.section('resource', self.resource, footnotes))
        lines.extend(self.section('filters', self.filters, footnotes))
        lines.extend(self.section('actions', self.actions, footnotes))
        return "\n".join(lines)

    def section(self, name, deprecations, footnotes):
        count = len(deprecations)
        if count == 0:
            return ()

        def footnote(d):
            if footnotes is None:
                return ""
            return footnotes.note(d)
        result = [f"  {name}:"]
        result.extend([f"    {d}{footnote(d)}" for d in deprecations])
        return result


class Footnotes:
    """A helper for defining and listing footnotes for deprecations.

    The deprecation date and URL being shown for every deprecation warning
    during validation would make the output repetitive and ungainly.

    This mechanism can allow for a note to be added at the end of each
    deprecation line and have the dates and URLs if they exist, shown at the
    end.
    """
    def __init__(self):
        self.seen = {}
        self.notes = []

    def note(self, d):
        """Return a reference to the footnote if the deprecation has one.

        A deprecation will have a footnote if either the remove_date or the URL are set.
        """
        if d.id not in self.seen:
            footnote = self._note(d)
            if not footnote:
                self.seen[d.id] = None
                return ""
            self.notes.append(footnote)
            ref = len(self.notes)
            self.seen[d.id] = ref
        else:
            ref = self.seen[d.id]
        if ref is None:
            return ""
        return f" [{ref}]"

    def _note(self, d):
        removed = d.remove_text
        if not removed and d.link is None:
            return ""
        text = ""
        if d.link is not None:
            text = f"See {d.link}"
            if removed:
                text += ", "
                removed = removed[0].lower() + removed[1:]
        if removed:
            text += removed
        return text

    def __call__(self):
        lines = []
        for i, note in enumerate(self.notes, 1):
            lines.append(f"[{i}] {note}")
        return "\n".join(lines)
