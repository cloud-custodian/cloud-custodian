.. _gcp_audit_event_recording:

Recording gcp-audit Event Fixtures
====================================

Tests for ``gcp-audit`` mode policies run
``exec_mode.run(event_data("some-event.json"), None)`` against a fixture
event -- a Cloud Audit Log ``LogEntry``. ``audit_event_recorder``, in
``tools/c7n_gcp/tests/gcp_common.py``, records those fixtures from real GCP
Cloud Audit Log entries instead of hand-writing synthetic event JSON, which
easily drifts from what GCP actually sends.

It only queries Cloud Logging -- no logging sink, Pub/Sub topic, or Cloud
Function is provisioned. That machinery is what a deployed ``gcp-audit``
policy uses to receive events at runtime; a test only needs the event data
itself.

Basic usage
------------

Construct the recorder *before* triggering the API call, so its polling
window starts early enough to catch the resulting log entry. Gate
``record()`` on ``test.recording`` -- it queries a live Cloud Logging
client, so it can't run against replayed flight data. Loading the fixture
for assertions always goes through the existing ``event_data(...)``,
regardless of mode:

.. code-block:: python

    from gcp_common import audit_event_recorder, event_data

    def test_firestore_backup_schedule_update(test, firestore_database):
        resource_name = firestore_database.resources[
            "google_firestore_backup_schedule"]["c7n"]["id"]

        session_factory = test.record_flight_data(
            "firestore-backup-schedule-update", project_id=project_id)

        recorder = audit_event_recorder(
            session_factory,
            "firestore-backup-schedule-update.json",
            method="UpdateBackupSchedule",
            resource_name=resource_name,
            labels={"database_id": database_id},
        )

        # trigger the real update here, e.g. a client.execute_command('patch', ...)
        # call, or a Terraform resource change

        if test.recording:
            recorder.record()

        event = event_data("firestore-backup-schedule-update.json")
        exec_mode = policy.get_execution_mode()
        resources = exec_mode.run(event, None)

Once recorded, commit the generated fixture(s) under
``tools/c7n_gcp/tests/data/events/`` and switch the test to
``replay_flight_data(...)``, same as any other flight-data test.

Filtering options
-------------------

``audit_event_recorder`` takes arguments to filter desired log events:

- ``method`` (required) -- a substring match against
  ``protoPayload.methodName``, e.g. ``"UpdateBackupSchedule"`` rather than
  the full ``google.firestore.admin.v1.FirestoreAdmin.UpdateBackupSchedule``.
- ``resource_name`` (optional) -- a substring match against
  ``protoPayload.resourceName``.
- ``labels`` (optional) -- an exact-match mapping against
  ``resource.labels``, e.g. ``{"database_id": database_id}``.
- ``start_time_skew`` (default 60s) -- how far before construction time to
  set the query's lower time bound, to guard against clock skew between
  the test host and Cloud Logging.
- ``timeout`` / ``poll_interval`` (default 120s/5s) -- how long, and how often, to poll
  before giving up.

``record()`` polls until every matching operation is complete (or the
timeout elapses), rather than issuing a single query -- Cloud Logging
entries can take a few seconds to become queryable after the underlying
API call completes. On timeout it raises, naming any operation still
missing its ``last`` entry; that usually means the filter is too loose and
swept up an unrelated operation, so narrow ``resource_name`` or ``labels``.

Files created
--------------

For a call with no `operation` field (see below), the matching entry is
written under the requested name, e.g. ``foo.json``.

If an entry belongs to a Cloud Logging *operation* (see below), the
filename reflects that:

- entries are grouped by ``operation.id``, and each distinct operation
  seen is assigned an index in the order first encountered (0, 1, 2, ...);
  index 0 is omitted from the filename, so the common single-operation
  case doesn't get a numeric suffix at all
- ``-first`` is appended when ``operation.first`` is set,
  ``-last`` when ``operation.last`` is set
- polling stops once *every* operation seen so far has produced its
  ``last`` entry -- one operation completing doesn't cut short another
  operation the same filter matched

So the common case for an operation-tracked method produces exactly two
files: ``foo-first.json`` and ``foo-last.json``. A second, distinct
operation swept up by the same filter (rare, but possible with a loose or no
``resource_name`` substring) would produce ``foo-1-first.json`` /
``foo-1-last.json``.

If a computed filename already exists on disk (e.g. a stale fixture from
an earlier recording run, or two truly ambiguous matches), a numeric
suffix is appended *after* the extension instead --
``foo.json``, then ``foo.json-1``, ``foo.json-2``, and so on -- and a
warning is logged. These extra files are left in place rather than
cleaned up automatically, so they show up in the diff for the developer
to sort out (rename, merge, or delete as appropriate).

Events and operations may have multiple log entries
-------------------------------------------------------

A single logical API call frequently produces more than one Cloud Audit
Log entry, correlated via a Cloud Logging ``LogEntryOperation``
(the top-level ``operation`` field: ``id``, ``first``, ``last``) rather
than anything under ``protoPayload``. Not every method uses this: many
produce exactly one, standalone log entry per call, with no ``operation``
field at all.

This matters for ``gcp-audit`` mode specifically because the deployed
Cloud Function's Logging sink filters only on ``protoPayload.methodName``.
Both the ``first`` and ``last`` rows of an operation-tracked call share
the same method name, so *both* independently match the sink filter and
get delivered as separate Pub/Sub messages -- meaning a real deployed
policy can be invoked twice for one real-world API call. Recording both
rows lets a test exercise the policy against either explicitly, rather
than assuming the deployed function only ever sees one event per call.

The two rows commonly carry different data: for update-type events the
``first`` row typically has everything (``request``, permission info) that
the ``last`` row lacks, with ``last`` mainly signalling completion (or
failure, via ``protoPayload.status``). For create-type events, the split
is less consistent -- see below.

Creation events don't always identify what was created
-----------------------------------------------------------

For "update" audit events, ``protoPayload.resourceName``
reliably names the specific resource being changed, since it already
exists and already has an assigned id.

For "create" audit events, that isn't reliable. Whether the
event identifies the *created* resource depends on whether the resource's
id is client-specified (e.g. a Dataproc cluster name, chosen by the
caller) or server-generated (e.g. a Firestore backup schedule id, a UUID
assigned by the API). When the id is server-generated,
``protoPayload.resourceName`` on the create event often names only the
*parent* resource, not the child being created -- and depending on the
service, the child's id may or may not show up elsewhere (``response``,
or the ``operation.id`` from the previous section). Some create events
provide no identity for the created resource anywhere in the log entry at
all.

Recorded event fixtures reflect this reality; a create-mode policy for a
resource type with server-generated ids may need resource-specific
handling (e.g. building a value directly from ``protoPayload.request``,
rather than resolving an id and calling ``get()``) instead of the generic
``resourceName``-based resolution that works for updates.
