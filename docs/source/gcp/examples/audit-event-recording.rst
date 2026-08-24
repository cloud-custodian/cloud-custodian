.. _gcp_audit_event_recording:

Recording gcp-audit Event Fixtures
====================================

Tests for ``gcp-audit`` mode policies run
``exec_mode.run(event_data("some-event.json"), None)`` against a
fixture event -- a Cloud Audit Log ``LogEntry``. The test helper,
``audit_event_recorder``, in ``tools/c7n_gcp/tests/gcp_common.py``,
records those fixtures from real GCP Cloud Audit Log entries instead
of hand-writing synthetic event JSON, which easily drifts from what
GCP actually sends.

Normally, when running ``gcp-audit`` mode policies, cloud resources are
created to invoke the policies when configured events occur, as
indicated by log entries.  The test helper avoids that by capturing
log entries directly.

Basic usage
------------

Recording is gated on ``test.recording``: it needs a live Cloud Logging
client, so it can't run against replayed flight data. Loading the fixture
for assertions always goes through ``event_data(...)``, regardless of mode.

API calls made by a recording run to *set up* an event, such as
triggering a resource change and polling Cloud Logging, are not
the behavior under test, and should not go through the test flight
recorder.  For that reason, a separate setup session is used.

Cloud Logging returns whole ``LogEntry`` objects, which include
sensitive developer data, such as email and IP addresses and
development project IDs. These are sanitized by the event recorder.

.. code-block:: python

    import functools

    from c7n_gcp.client import Session
    from gcp_common import audit_event_recorder, event_data

    @terraform("firestore_database")
    def test_firestore_backup_schedule_update(test, firestore_database):
        resource_name = firestore_database.resources[
            "google_firestore_backup_schedule"]["c7n"]["id"]

        policy_session_factory = test.replay_flight_data(
            "firestore-backup-schedule-update", project_id=project_id)

        if test.recording:
            # Use a separate session for event recording:
            setup_session_factory = functools.partial(
                Session, project_id=project_id)
            setup_session = setup_session_factory()

            # trigger the real change here, e.g.
            # setup_session.client(...).execute_command("patch", ...)

            audit_event_recorder(
                setup_session_factory,

                # Base name for recorded event-data files:
                "firestore-backup-schedule-update.json",

                # Required event operation method-name to record:
                method="UpdateBackupSchedule",

                # Additional filters
                resource_name=resource_name,
                labels={"database_id": database_id},

                # Use a large skew to capture create events performed
                # by Terraform.
                start_time_skew=900,

                ).record()

            # Prevent the cached setup session from being reused:
            test.cleanUp()

        policy = test.load_policy(
            {...}, session_factory=policy_session_factory)
        [resource] = policy.get_execution_mode().run(
            event_data("firestore-backup-schedule-update.json"), None)

The recorder takes a session *factory*, not a session, which is why
``setup_session_factory`` is kept around after being called.

``test.cleanUp()`` at the end of the block is required, not tidiness. A
session (keyed by region, in ``c7n.utils.CONN_CACHE``) and its http
transport (keyed by thread, by ``Session.http``) are both cached globally,
ignoring the factory the caller asked for. Without it the policy below
reuses ``setup_session``, so nothing is written to flight data -- and the
test still passes, against the live api. For the same reason, build the
setup session directly rather than through ``local_session()``.

The ``start_time_skew`` parameter, as its name implies, is normally
used to adjust for clock skew and defaults to 60 seconds.  It can also
be used to work around the fact that the event recorder is created in
the test body, after Terraform has created test resources.  Future
versions of the test helper will make this unnecessary.

While actually recording, the flight-data and Terraform decorators take
their recording forms -- ``test.record_flight_data(...)`` and
``@terraform("firestore_database", replay=False)``. Once recorded, commit
the generated fixture(s) under ``tools/c7n_gcp/tests/data/events/`` and
switch both back, same as any other flight-data test.

``test_disk_audit_mode``, in ``tools/c7n_gcp/tests/test_compute.py``, is a
worked example.

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
  set the query's lower time bound. The default covers clock skew between
  the test host and Cloud Logging, assuming the recorder is constructed
  around the time the event is triggered. Raise it when the event happened
  earlier -- notably for a resource a ``@terraform`` fixture created before
  the test body ran.
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

Some GCP operations have multiple log entries.  These log entries have
an ``operation`` field with an ``id`` field used to group them together.

For a call with no ``operation`` field, the matching entry is
written under the requested name, e.g. ``foo.json``.

If an entry has an ``operation`` field, the
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

So the common case for an operation with multiple log entries produces
exactly two files: ``foo-first.json`` and ``foo-last.json``. A second,
distinct operation swept up by the same filter (rare, but possible
with a loose or no ``resource_name`` substring) would produce
``foo-1-first.json`` / ``foo-1-last.json``.

If a computed filename already exists on disk (e.g. a stale fixture from
an earlier recording run, or two truly ambiguous matches), a numeric
suffix is appended *after* the extension instead --
``foo.json``, then ``foo.json-1``, ``foo.json-2``, and so on -- and a
warning is logged. These extra files are left in place rather than
cleaned up automatically, so they show up in the diff for the developer
to sort out (rename, merge, or delete as appropriate).

Sanitization
-------------

Recorded entries are rewritten before being written to disk:

- the recording account's project id becomes ``cloud-custodian``, the same
  placeholder ``recorder.py`` uses for flight data -- an event naming the
  real project would resolve its resource against a project that has no
  recorded responses
- any email address becomes ``user@example.com``
- ``protoPayload.requestMetadata.callerIp`` becomes ``198.51.100.1``

Other projects an entry refers to (a public image project, say) are left
alone, as is the ``oauthClientId``, which identifies the client
application rather than the caller.

Caveats
-------

Multiple log entries cause multiple policy invocations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

As mentioned earlier, an operation may have multiple log entries. A
matching policy will be invoked for each entry.

Creation events don't always identify what was created
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For "update" audit events, ``protoPayload.resourceName``
reliably names the specific resource being changed, since it already
exists and already has an assigned id.

For "create" audit events, that isn't reliable. Whether the
event identifies the *created* resource depends on the resource type.
For some resources, ``resourceName`` names some other resource that
serves the role of a factory.  In some, but not all, cases, the
identity of the created resource occurs somewhere in log entries in a
resource-type dependent way.
