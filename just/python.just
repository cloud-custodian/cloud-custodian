set working-directory := ".."

@_default:
    just --list python

# Subset of packages that use black for formatting.
FMT_SET := "tools/c7n_left tools/c7n_mailer tools/c7n_oci tools/c7n_kube tools/c7n_awscc"

# Ruff + black lint checks (no modifications).
@lint:
    uv run --no-project ruff check c7n tests tools
    uv run --no-project black --check {{FMT_SET}}
    terraform fmt -check -recursive .

# Apply ruff + black auto-fixes and terraform formatting.
@format:
    uv run black {{FMT_SET}}
    uv run ruff check --fix c7n tests tools
    terraform fmt -recursive .

# Run the full test suite.
@test *ARGS:
    uv run pytest -n auto {{ARGS}} tests tools

# Coverage report format: html (default), term, xml, etc.
COVERAGE_TYPE := env_var_or_default("COVERAGE_TYPE", "html")

# Run the test suite with coverage report.
@coverage *ARGS:
    uv run pytest -n auto \
        --cov-config .coveragerc \
        --cov-report {{COVERAGE_TYPE}} \
        --cov c7n \
        --cov tools/c7n_azure/c7n_azure \
        --cov tools/c7n_gcp/c7n_gcp \
        --cov tools/c7n_kube/c7n_kube \
        --cov tools/c7n_left/c7n_left \
        --cov tools/c7n_mailer/c7n_mailer \
        --cov tools/c7n_policystream/c7n_policystream \
        --cov tools/c7n_tencentcloud/c7n_tencentcloud \
        --cov tools/c7n_oci/c7n_oci \
        tests tools {{ARGS}}

# Run functional tests against a real AWS environment (provisions real resources).
@test-functional *ARGS:
    C7N_FUNCTIONAL=yes AWS_DEFAULT_REGION=us-east-2 pytest tests -m functional {{ARGS}}

# Run functional tests against a real Azure environment (provisions real resources).
@test-functional-azure *ARGS:
    C7N_FUNCTIONAL=yes uv run pytest tools/c7n_azure/tests_azure -k terraform -m functional {{ARGS}}
