- [Local development](#local-development)
  - [Install the development dependencies](#install-the-development-dependencies)
  - [Setup environment variables](#setup-environment-variables)
  - [Running the tests](#running-the-tests)
    - [Using the Makefile (recommended)](#using-the-makefile-recommended)
    - [Running GCP tests directly](#running-gcp-tests-directly)
    - [Using the virtual environment directly](#using-the-virtual-environment-directly)
  - [Authentication](#authentication)
    - [Application Default Credentials (ADC)](#application-default-credentials-adc)
    - [Managing Multiple GCP Accounts](#managing-multiple-gcp-accounts)
    - [Verifying Authentication](#verifying-authentication)
  - [Testing Patterns](#testing-patterns)
    - [Flight Data Recording](#flight-data-recording)
      - [Test Structure](#test-structure)
      - [Test Modes](#test-modes)
        - [Playback Mode (Default)](#playback-mode-default)
      - [Recording Mode](#recording-mode)
      - [Writing Tests](#writing-tests)
        - [Basic Test Pattern](#basic-test-pattern)
        - [Tests with Terraform Infrastructure](#tests-with-terraform-infrastructure)
      - [File Locations](#file-locations)
      - [Recording New Flight Data](#recording-new-flight-data)
      - [Best Practices](#best-practices)
  - [Troubleshooting](#troubleshooting)
    - [Quota Project](#quota-project)


# Local development

If you are just interested in doing local development with GCP, and not the
whole c7n collection, then you can do the following.

## Install the development dependencies

This project is part of a uv workspace. You need to install from the **root**
of the cloud-custodian repository (not from the `tools/c7n_gcp` directory).

From the repository root, use the Makefile target:

    make install

This runs:

    uv sync --all-packages --locked --group dev --group addons --group lint --extra gcp --extra azure

Where:
- `--all-packages` installs all workspace members (including c7n_gcp) in editable mode
- `--locked` ensures reproducible installs using the lock file
- `--group dev` installs development dependencies (pytest, etc.)
- `--group addons` installs optional addons
- `--group lint` installs linting tools (ruff, black)
- `--extra gcp --extra azure` installs optional extras for c7n_mailer

**Note:** `uv sync` automatically creates a virtual environment at `.venv` in the
repository root if one doesn't exist. You don't need to create or activate a virtual
environment before running the install command. However, if you want to use the
environment directly (without `uv run`), you'll need to activate it:

    source .venv/bin/activate

## Setup environment variables

Tests are run from the repository root and require environment variables. These are
set in `test.env` in the repository root directory.

    export GOOGLE_CLOUD_PROJECT=custodian-1291
    export GOOGLE_APPLICATION_CREDENTIALS=tests/data/credentials.json

The Makefile automatically sources `test.env` when running tests.

If desired you can also set these environment variables to your own personal project and credentials during active development.

## Running the tests

Tests should be run from the **repository root** (not from the `tools/c7n_gcp` directory).

### Using the Makefile (recommended)

Run all tests (including GCP):

    make test

Run only the GCP test suite:

    make test-gcp

This automatically sources `test.env` and runs tests with parallel execution.

### Running GCP tests directly

To run just the GCP tests with parallel execution:

    uv run pytest -n auto tools/c7n_gcp/tests

To run a specific test file:

    uv run pytest tools/c7n_gcp/tests/test_compute.py

To run with additional arguments:

    uv run pytest -n auto tools/c7n_gcp/tests -v -x

Note: When running tests directly (not via `make test`), you need to manually source
the environment variables:

    source test.env
    uv run pytest -n auto tools/c7n_gcp/tests

### Using the virtual environment directly

Alternatively, you can activate the virtual environment:

    source .venv/bin/activate
    source test.env
    pytest -n auto tools/c7n_gcp/tests


## Authentication

For local development and testing, you need to authenticate with Google Cloud Platform.

### Application Default Credentials (ADC)

The recommended approach is to use Application Default Credentials:

    gcloud auth application-default login

This creates credentials at `~/.config/gcloud/application_default_credentials.json` that are
automatically used by the Google Cloud SDK, Terraform, and other tools.

### Managing Multiple GCP Accounts

If you work with multiple GCP accounts or projects, use multiple ADC files with
environment variable switching:

    # Login to first account and save credentials
    gcloud auth application-default login
    cp ~/.config/gcloud/application_default_credentials.json \
       ~/.config/gcloud/adc-work.json

    # Login to second account and save credentials
    gcloud auth application-default login
    cp ~/.config/gcloud/application_default_credentials.json \
       ~/.config/gcloud/adc-personal.json

    # Switch accounts by setting environment variable
    export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/adc-work.json
    # or
    export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/adc-personal.json


### Verifying Authentication

Check your current authentication status:

    # Check CLI account
    gcloud auth list

    # Verify ADC works
    gcloud auth application-default print-access-token

    # Check active project
    gcloud config get-value project

    # Set project if not set by environment variable
    gcloud config set project <project-id>

## Testing Patterns

### Flight Data Recording
GCP tests use a "flight data" recording pattern with Terraform for infrastructure provisioning.

#### Test Structure

Tests inherit from `BaseTest` (defined in `tools/c7n_gcp/tests/gcp_common.py`) which provides:
- `record_flight_data(test_case)` - Records real API calls to flight data files
- `replay_flight_data(test_case)` - Replays from recorded flight data files
- `load_policy(policy_dict)` - Loads and validates a Cloud Custodian policy
Flight data files are HTTP request/response recordings stored in:
- **Location**: `tools/c7n_gcp/tests/data/flights/<test-case-name>/`
- **Format**: JSON files containing HTTP headers and response bodies
- **Purpose**: Enable tests to run without real GCP API calls

#### Test Modes

##### Playback Mode (Default)

Runs tests using recorded flight data - no real API calls or GCP credentials needed:

    uv run pytest tools/c7n_gcp/tests/test_artifactregistry.py::ArtifactRegistryTest::test_artifact_repository_label -xvs

#### Recording Mode

Makes real GCP API calls and records responses to flight data files:

    C7N_FUNCTIONAL=yes uv run pytest tools/c7n_gcp/tests/test_artifactregistry.py::ArtifactRegistryTest::test_artifact_repository_label -xvs

**Requirements for recording:**
- Valid GCP credentials (via `gcloud auth application-default login`)
- `GOOGLE_CLOUD_PROJECT` environment variable set
- Terraform installed (for tests using `@terraform` decorator)

#### Writing Tests

##### Basic Test Pattern

```python
from gcp_common import BaseTest

class ArtifactRegistryTest(BaseTest):

    def test_artifact_repository_label(self, artifact_repository):
        # replay_flight_data automatically switches to recording mode when C7N_FUNCTIONAL=yes
        factory = self.record_flight_data('artifact-repository-label')

        # Test implementation
        p = self.load_policy({
            'name': 'artifact-repository-label',
            'resource': 'gcp.artifact-repository',
            'filters': [{'type': 'value', 'key': 'format', 'value': 'DOCKER'}]
        }, session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
```

##### Tests with Terraform Infrastructure

For tests requiring real GCP resources, use the `@terraform` decorator:

```python
from gcp_common import BaseTest
from pytest_terraform import terraform

class ArtifactRegistryTest(BaseTest):

    @terraform('artifact_repository')
    def test_artifact_repository_label(self, artifact_repository):
        # replay_flight_data automatically switches to recording mode when C7N_FUNCTIONAL=yes
        factory = self.replay_flight_data('artifact-repository-label')

        # Test implementation
        p = self.load_policy({
            'name': 'artifact-repository-label',
            'resource': 'gcp.artifact-repository',
            'filters': [{'type': 'value', 'key': 'format', 'value': 'DOCKER'}]
        }, session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
```

**How `@terraform` works:**
1. Looks for Terraform config at `tools/c7n_gcp/tests/terraform/<name>/main.tf`
2. In recording mode (`C7N_FUNCTIONAL=yes`):
   - Deploys real GCP resources using Terraform
   - Generates `tf_resources.json` with resource details
   - Records API responses to flight data files
3. In playback mode:
   - Skips Terraform deployment
   - Uses recorded flight data

#### File Locations

```
tools/c7n_gcp/tests/
├── terraform/                    # Terraform configurations
│   ├── artifact_repository/
│   │   ├── main.tf              # Terraform config
│   │   └── tf_resources.json    # Generated resource data (recording mode)
├── data/
│   └── flights/                 # Recorded flight data
│       ├── artifact-repository-label/
│       │   ├── get-v1-projects-..._1.json
│       │   └── post-v1-repositories_1.json
└── test_*.py                    # Test files
```

#### Recording New Flight Data

1. **Ensure authentication is configured:**
   ```bash
   gcloud auth application-default login
   export GOOGLE_CLOUD_PROJECT=your-project-id
   ```

2. **Delete existing flight data** (if re-recording):
   ```bash
   rm -rf tools/c7n_gcp/tests/data/flights/test-case-name/
   ```

3. **Run test in recording mode:**
   ```bash
   C7N_FUNCTIONAL=yes uv run pytest tools/c7n_gcp/tests/test_compute.py::test_instance_label -xvs
   ```

#### Best Practices

- **Use descriptive test case names** - The name passed to `record_flight_data()` becomes the directory name
- **Commit flight data** - Required for CI/CD pipelines to run tests
- **Use Terraform for complex resources** - Ensures reproducible test infrastructure
- **Clean up resources** - Terraform automatically destroys resources after tests in recording mode

## Troubleshooting

### Quota Project

If you get the following warnings when making api calls take the following remediation steps:

```
UserWarning: Your application has authenticated using end user credentials from Google Cloud SDK without a quota project. You might receive a "quota exceeded" or "API not enabled" error. See the following page for troubleshooting: https://cloud.google.com/docs/authentication/adc-troubleshooting/user-creds.
```

If you are using the default credential (~/.config/gcloud/application_default_credentials.json) you can run the following command to set the quota project:
```
gcloud auth application-default set-quota-project <PROJECT_ID>
```

If you are using named credential files modify the file directly to include the quota project `"quota_project_id": "<PROJECT_ID>"`:
