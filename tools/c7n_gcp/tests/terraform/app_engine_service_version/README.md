# App Engine Service Version Recording

This fixture deploys two App Engine standard versions to the `default` service:
one whose `/.*` handler is `SECURE_ALWAYS` and one whose handler is
`SECURE_OPTIONAL`.

## Prerequisites

- **An App Engine application.** Applications can't be deleted and their region
  can't change, so a fixture that created one could only ever apply once.

  ```bash
  gcloud app create --region=us-central
  ```

- **A version in `default` that outlives the fixture.** App Engine won't delete
  the last version of a service. In a new app, the first recording's teardown
  fails with "Cannot delete the final version of a service", leaving one `c7n-*`
  version and the `c7n-app-engine-*` bucket. The recordings are still good. Keep
  the version, since it's the one later recordings need, and delete the bucket:

  ```bash
  gcloud storage rm --recursive gs://<bucket>
  ```

  Later recordings tear down cleanly.

- **APIs enabled:**

  ```bash
  gcloud services enable appengine.googleapis.com cloudbuild.googleapis.com \
    storage.googleapis.com artifactregistry.googleapis.com
  ```

- **Application default credentials** for the project:

  ```bash
  gcloud auth application-default login
  ```

## Recording

Delete the old audit events first. The recorder won't overwrite an event file;
it writes `<name>.json-1` beside it, and the test keeps reading the old one:

```bash
rm tools/c7n_gcp/tests/data/events/app-engine-version-create-*.json
```

Switch both `test_app_engine_service_version_*` tests in `test_appengine.py` to
`replay=False` and `record_flight_data`, then run:

```bash
C7N_FUNCTIONAL=yes GOOGLE_CLOUD_PROJECT=<project> \
  uv run pytest -s -p no:env --tf-debug \
  tools/c7n_gcp/tests/test_appengine.py -k app_engine_service_version
```

`C7N_FUNCTIONAL=yes` makes `event_data` put the live project back into the
recorded audit events, so the audit test fetches a version that exists.

The recorder only rewrites `projects/<id>/`, and App Engine paths are
`apps/<id>/`. Before committing:

- rename the flight files and replace the project id with `cloud-custodian`, in
  the flight data and in `tf_resources.json`
- replace `createdBy` with `user@example.com`, and the bucket's `project_number`
  in `tf_resources.json` with `123456789012`

Then remove `replay=False` and switch back to `replay_flight_data` in both
tests, and confirm they pass in replay:

```bash
C7N_FUNCTIONAL=no uv run pytest \
  tools/c7n_gcp/tests/test_appengine.py -k app_engine_service_version
```

## Cleanup check

```bash
gcloud app versions list --project <project>
gcloud storage buckets list --project <project> --filter='name~c7n-app-engine'
```

Only the long-lived `default` version should remain, and no `c7n-app-engine-*`
bucket.
