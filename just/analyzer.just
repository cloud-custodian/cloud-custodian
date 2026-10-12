set working-directory := ".."

@_default:
    just --list analyzer

# Directories analysed by both bandit and semgrep.
# B105 (hardcoded password) is skipped — see https://github.com/PyCQA/bandit/issues/1350
ANALYZE_DIRS := "tools/c7n_azure/c7n_azure \
    tools/c7n_gcp/c7n_gcp \
    tools/c7n_oci/c7n_oci \
    tools/c7n_left/c7n_left \
    tools/c7n_guardian/c7n_guardian \
    tools/c7n_org/c7n_org \
    tools/c7n_mailer/c7n_mailer \
    tools/c7n_policystream/policystream.py \
    tools/c7n_trailcreator/c7n_trailcreator \
    c7n"

# Run bandit static analysis (skips B101, B105, B311).
@bandit:
    uvx bandit -i -s B101,B105,B311 -r {{ANALYZE_DIRS}}

# Run semgrep security audit.
@semgrep:
    uvx semgrep --error --verbose --config p/security-audit {{ANALYZE_DIRS}}

# Run all static analyzers.
@all:
    just analyzer bandit
    just analyzer semgrep
