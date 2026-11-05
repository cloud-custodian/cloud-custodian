.. _gcp_recorded_event_fixture:

Packaged audit event fixture
===========================

``c7n_gcp.testing`` provides an opt-in pytest fixture for capturing Cloud
Audit Log entries and replaying them without querying Cloud Logging. It is
included in the provider wheel. Install pytest in the consuming test suite;
pytest-terraform is only needed when using Terraform fixtures.

In your top-level ``conftest.py``, register the plugin::

    pytest_plugins = ["c7n_gcp.testing"]

The suite must provide its existing ``test`` fixture, whose ``recording``
attribute selects live mode when no Terraform fixture is present. The GCP
test suite already imports these fixtures and the Terraform setup hook.

Example::

    @terraform("setup_thing", scope="module")
    def test_created_thing(test, setup_thing, recorded_event):
        resource_name = setup_thing["google_compute_instance.thing.id"]
        event = recorded_event(resource_name, "insert")
        # Pass event to the policy's gcp-audit execution mode.

The setup hook captures time before each Terraform fixture runs, including
module and session scopes. The earliest setup time is the query's lower
bound. Terraform replay mode takes precedence over ``test.recording``;
mixed recording and replay Terraform fixtures raise an error. Without
Terraform, the lower bound is the event fixture's setup time and recording
mode is read on the first lookup. Trigger the operation after fixture setup.

Cloud Logging calls use a separate session with explicit credentials. This
avoids the policy flight recorder's cached HTTP transport. Replay never
constructs that session or falls back to the live API.

Selection
---------

The returned callable accepts ``resource_name``, ``method``, ``labels=None``,
``jmespath=None``, ``first=False``, ``timeout_seconds=120``,
``poll_interval_seconds=5``, and ``after=None``.

Resource name and method use Cloud Logging substring matching; labels are
exact matches against ``resource.labels``. Queries cover Admin Activity
logs. Creation events do not always name the new resource in resourceName;
use the identity present in the service's actual audit entry.

Records are grouped by operation producer and ID. Unpaired records count as
individual operations. By default the completion record is returned; with
``first=True`` the initial record is returned. A single record with no
first/last flags, or with both flags set, supports either selection.

Multiple operations raise an ambiguity error unless ``after`` is supplied:

* ``after=-1`` selects the first operation in timestamp order.
* ``after=0`` selects the second operation, and so on.
* An event dictionary or UTC ISO timestamp selects the first operation
  starting strictly after its timestamp. Nanosecond precision is preserved.

The JMESPath expression is a predicate: an operation is retained if any of
its records matches. Its terminal record remains available even when only
the initial record matches. Missing or incomplete live operations are polled
until timeout. Visibility is limited to records returned by Cloud Logging;
later arriving operations can introduce ambiguity in a subsequent lookup.
Repeated identical successful lookups within a test return independent
copies of the same result.

Recordings
----------

Override ``event_log_recording_directory`` to choose the recording directory.
Its default is ``data/events/<test-name>`` beside the test module. Each
resource/method/labels query gets a deterministic JSON filename; first,
after, and JMESPath selectors share that query's recorded entries.

Records on disk replace the live project with ``cloud-custodian``, email
addresses with ``user@example.com``, and caller IPs with ``198.51.100.1``.
Returned live entries retain their original identity for policy execution;
replayed entries use the placeholders. Review generated files before
committing them. No policy API flight recordings are produced by this helper.

The legacy ``gcp_common.audit_event_recorder`` remains available, with a
DeprecationWarning, so existing consumers can migrate separately.
