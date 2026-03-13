# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
SHELL := /bin/bash
SELF_MAKE := $(lastword $(MAKEFILE_LIST))

PKG_REPO = testpypi
PKG_INCREMENT := patch
PKG_SET := tools/c7n_gcp tools/c7n_kube tools/c7n_openstack tools/c7n_mailer tools/c7n_policystream tools/c7n_org tools/c7n_sphinxext tools/c7n_awscc tools/c7n_tencentcloud tools/c7n_azure tools/c7n_oci tools/c7n_left

PKG_SET_OLD := tools/c7n_logexporter tools/c7n_trailcreator tools/c7n_terraform

FMT_SET := tools/c7n_left tools/c7n_mailer tools/c7n_oci tools/c7n_kube tools/c7n_awscc

COVERAGE_TYPE := html
ARGS :=
IMAGE := c7n
IMAGE_TAG := latest

###
# Common developer targets

install:
# extras are for c7n_mailer, separate lint from dev for ci
	uv sync --all-packages --locked \
	    --group dev \
	    --group addons \
	    --group lint \
            --extra gcp --extra azure

.PHONY: test

test:
	uv run pytest -n auto $(ARGS) tests tools

test-coverage:
	uv run pytest -n auto \
            --cov-config .coveragerc \
            --cov-report $(COVERAGE_TYPE) \
            --cov c7n \
            --cov tools/c7n_azure/c7n_azure \
            --cov tools/c7n_gcp/c7n_gcp \
            --cov tools/c7n_kube/c7n_kube \
            --cov tools/c7n_left/c7n_left \
            --cov tools/c7n_mailer/c7n_mailer \
            --cov tools/c7n_policystream/c7n_policystream \
            --cov tools/c7n_tencentcloud/c7n_tencentcloud \
            --cov tools/c7n_oci/c7n_oci \
            tests tools $(ARGS)

diff-coverage:
	@echo "Checking for diff-cover..."
	# This overcomes dependency issues with packages in pyproject.toml
	@if ! uv tool list | grep -q "^diff-cover"; then \
		echo "diff-cover not found. Installing as a tool..."; \
		uv tool install diff-cover; \
	else \
		echo "diff-cover is already installed"; \
	fi
	@echo "Running tests with coverage for changed files..."
	@CHANGED_TEST_FILES=$$(git diff --name-only origin/main | grep -E "test_.*\.py$$" || true); \
	if [ -z "$$CHANGED_TEST_FILES" ]; then \
		echo "Error: No test files changed compared to origin/main"; \
		echo "Use 'make diff-coverage-full' to run all tests for a provider, or specify TEST_PATH=<path>"; \
		exit 1; \
	fi; \
	echo "Running changed test files:"; \
	echo "$$CHANGED_TEST_FILES" | sed 's/^/  - /'; \
	uv run pytest $$CHANGED_TEST_FILES -n auto \
		--cov-config .coveragerc \
		--cov-report xml \
		--cov-report term-missing \
		--cov c7n \
		--cov tools/c7n_azure/c7n_azure \
		--cov tools/c7n_gcp/c7n_gcp \
		--cov tools/c7n_kube/c7n_kube \
		--cov tools/c7n_left/c7n_left \
		--cov tools/c7n_mailer/c7n_mailer \
		--cov tools/c7n_policystream/c7n_policystream \
		--cov tools/c7n_tencentcloud/c7n_tencentcloud \
		--cov tools/c7n_oci/c7n_oci \
		-v
	@echo ""
	@echo "Generating diff coverage report..."
	@uv tool run diff-cover coverage.xml --compare-branch=origin/main --html-report htmlcov/diff-coverage.html
	@echo ""
	@echo "HTML report generated: htmlcov/diff-coverage.html"
	@echo "Run 'make view-diff-coverage' to open the report in your browser"

view-coverage:
	@if [ ! -f htmlcov/index.html ]; then \
		echo "Error: htmlcov/index.html not found"; \
		echo "Run 'make test-coverage' first to generate the full coverage report"; \
		exit 1; \
	fi
	@xdg-open htmlcov/index.html 2>/dev/null || open htmlcov/index.html 2>/dev/null || echo "Please open htmlcov/index.html manually"

view-diff-coverage:
	@if [ ! -f htmlcov/diff-coverage.html ]; then \
		echo "Error: htmlcov/diff-coverage.html not found"; \
		echo "Run 'make diff-coverage' or 'make diff-coverage-full' first to generate the diff coverage report"; \
		exit 1; \
	fi
	@xdg-open htmlcov/diff-coverage.html 2>/dev/null || open htmlcov/diff-coverage.html 2>/dev/null || echo "Please open htmlcov/diff-coverage.html manually"

test-functional:
# note this will provision real resources in a cloud environment
	C7N_FUNCTIONAL=yes AWS_DEFAULT_REGION=us-east-2 pytest tests -m functional $(ARGS)

test-functional-azure:
# note this will provision real resources in Azure's public cloud environment
	C7N_FUNCTIONAL=yes uv run pytest tools/c7n_azure/tests_azure/tests_resources/test_entraid.py -k terraform -m functional $(ARGS)

sphinx:
	make -f docs/Makefile.sphinx html

lint:
	uv run --no-project ruff check c7n tests tools
	uv run --no-project black --check $(FMT_SET)
	terraform fmt -check -recursive .

format:
	uv run black $(FMT_SET)
	uv run ruff check --fix c7n tests tools
	terraform fmt -recursive .

clean:
	make -f docs/Makefile.sphinx clean
	rm -rf .tox .Python bin include lib pip-selfcheck.json
	@$(MAKE) -f $(SELF_MAKE) pkg-clean

image:
	docker build -f docker/$(IMAGE) -t $(IMAGE):$(IMAGE_TAG) .

gen-docker:
	uv run tools/dev/dockerpkg.py generate
###
# Package Management Targets
# - primarily used to help drive frozen releases and dependency upgrades

pkg-clean:
	rm -f release.md
	rm -f wheels-manifest.txt
	rm -f dist/*
	for pkg in $(PKG_SET); do cd $$pkg && rm -f dist/* && cd ../..; done

	rm -Rf build/*
	for pkg in $(PKG_SET); do cd $$pkg && rm -Rf build/* && cd ../..; done


pkg-update:
	uv sync --all-packages \
	    --group dev \
	    --group addons \
	    --group lint \
            --extra gcp --extra azure \
            --upgrade

pkg-show-update:
	uv tree --outdated --no-default-groups

pkg-increment:
# increment versions
	uv version --bump $(PKG_INCREMENT)
	for pkg in $(PKG_SET); do cd $$pkg && uv version --bump $(PKG_INCREMENT) && cd ../..; done
	uv run tools/dev/devpkg.py gen-version-file -p . -f c7n/version.py

pkg-build-wheel:
	@$(MAKE) -f $(SELF_MAKE) pkg-clean
	uv build --all-packages --wheel
	uv run tools/dev/freezeuvwheel.py dist uv.lock
	uv run twine check --strict dist/*.whl

pkg-publish-wheel:
# upload to named package index / pypi
	uv run twine upload -r $(PKG_REPO) dist/*

release-get-artifacts:
# download release artifacts from github release action
	@$(MAKE) -f $(SELF_MAKE) pkg-clean
	uv run tools/dev/get_release_artifacts.py

data-update:
# terraform data sets
	cd tools/c7n_left/scripts && uv run python get_taggable.py \
		--module-path taggable_providers/latest \
		--module-path taggable_providers/azurerm-previous \
		--output ../c7n_left/data/taggable.json
# aws data sets
	uv run python tools/dev/data_cftypedb.py -f tests/data/cfn-types.json
	uv run python tools/dev/data_updatearnref.py > tests/data/arn-types.json
	uv run python tools/dev/data_iamdb.py -f tests/data/iam-actions.json
# gcp data sets
	uv run python tools/dev/data_gcpiamdb.py -f tools/c7n_gcp/tests/data/iam-permissions.json
	uv run python tools/dev/data_gcpregion.py -f tools/c7n_gcp/c7n_gcp/regions.json
###
# Static analyzers

# For context around skipping the B105 (hardcoded password)
# rule, see:
# https://github.com/PyCQA/bandit/issues/1350
analyzer-bandit:
	uvx bandit -i -s B101,B105,B311 \
	-r tools/c7n_azure/c7n_azure \
	 tools/c7n_gcp/c7n_gcp \
	 tools/c7n_oci/c7n_oci \
	 tools/c7n_left/c7n_left \
	 tools/c7n_guardian/c7n_guardian \
	 tools/c7n_org/c7n_org \
	 tools/c7n_mailer/c7n_mailer \
	 tools/c7n_policystream/policystream.py \
	 tools/c7n_trailcreator/c7n_trailcreator \
	 c7n


analyzer-semgrep:
	uvx semgrep --error --verbose --config p/security-audit \
	 tools/c7n_azure/c7n_azure \
	 tools/c7n_gcp/c7n_gcp \
	 tools/c7n_oci/c7n_oci \
	 tools/c7n_left/c7n_left \
	 tools/c7n_guardian/c7n_guardian \
	 tools/c7n_org/c7n_org \
	 tools/c7n_mailer/c7n_mailer \
	 tools/c7n_policystream/policystream.py \
	 tools/c7n_trailcreator/c7n_trailcreator \
	 c7n
