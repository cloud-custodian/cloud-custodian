set working-directory := ".."

@_default:
    just --list pkg

PKG_SET := "tools/c7n_gcp tools/c7n_kube tools/c7n_openstack tools/c7n_mailer \
    tools/c7n_policystream tools/c7n_org tools/c7n_sphinxext tools/c7n_awscc \
    tools/c7n_tencentcloud tools/c7n_azure tools/c7n_oci tools/c7n_left"

# Package index to publish to (default: testpypi).
PKG_REPO := env_var_or_default("PKG_REPO", "testpypi")

# Version component to bump (default: patch).
PKG_INCREMENT := env_var_or_default("PKG_INCREMENT", "patch")

# Remove all dist/ and build/ artefacts across the workspace.
@clean:
    #!/usr/bin/env bash
    set -euo pipefail
    rm -f release.md wheels-manifest.txt
    rm -f dist/*
    for pkg in {{PKG_SET}}; do
        rm -f "$pkg/dist/"*
    done
    rm -Rf build/*
    for pkg in {{PKG_SET}}; do
        rm -Rf "$pkg/build/"*
    done

# Upgrade all locked dependencies.
@update:
    uv sync --all-packages \
        --group dev \
        --group addons \
        --group lint \
        --extra gcp --extra azure \
        --upgrade

# Show outdated dependencies.
@show-update:
    uv tree --outdated --no-default-groups

# Bump version for all packages (PKG_INCREMENT=patch|minor|major).
@increment:
    #!/usr/bin/env bash
    set -euo pipefail
    uv version --bump {{PKG_INCREMENT}}
    for pkg in {{PKG_SET}}; do
        (cd "$pkg" && uv version --bump {{PKG_INCREMENT}})
    done
    uv run tools/dev/devpkg.py gen-version-file -p . -f c7n/version.py

# Build wheels for all packages (runs clean first).
@build-wheel: clean
    uv build --all-packages --wheel
    uv run tools/dev/freezeuvwheel.py dist uv.lock
    uv run twine check --strict dist/*.whl

# Publish wheels to PKG_REPO.
@publish:
    uv run twine upload -r {{PKG_REPO}} dist/*

# Download release artefacts from the GitHub release action (runs clean first).
@get-artifacts: clean
    uv run tools/dev/get_release_artifacts.py
