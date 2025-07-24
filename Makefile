# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
oSHELL := /bin/bash
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
	. $(PWD)/test.env && uv run pytest -n auto $(ARGS) tests tools

test-coverage:
	. $(PWD)/test.env && uv run pytest -n auto \
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

test-functional:
# note this will provision real resources in a cloud environment
	C7N_FUNCTIONAL=yes AWS_DEFAULT_REGION=us-east-2 pytest tests -m functional $(ARGS)

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
	cd tools/c7n_left/scripts && python uv run get_taggable.py \
		--module-path taggable_providers/latest \
		--module-path taggable_providers/azurerm-previous \
		--output ../c7n_left/data/taggable.json
# aws data sets
	uv run tools/dev/data_cfntypedb.py -f tests/data/cfn-types.json
	uv run tools/dev/data_updatearnref.py > tests/data/arn-types.json
	uv run tools/dev/data_iamdb.py -f tests/data/iam-actions.json
# gcp data sets
	uv run tools/dev/data_gcpiamdb.py -f tools/c7n_gcp/tests/data/iam-permissions.json
	uv run tools/dev/data_gcpregion.py -f tools/c7n_gcp/c7n_gcp/regions.json

###
# Static analyzers

analyzer-bandit:
	uvx bandit -i -s B101,B311 \
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

###
# Everything below here is just for ZOE's use
###

.PHONY: zoe-image-push
zoe-image-push:
	@echo "This will push the cloud custodian image to GCP, you will need permissions to push to artifact registry."
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ]
	docker build \
		-f docker/c7n \
		--platform linux/amd64 \
		-t europe-west1-docker.pkg.dev/backend-producti-b8633498/zoe-custom-images/cloud_custodian:latest \
		.
	docker push europe-west1-docker.pkg.dev/backend-producti-b8633498/zoe-custom-images/cloud_custodian:latest


test-gcp-policy:
	@echo "Running GCP policy test..."
	@if [ -z "$$GOOGLE_CLOUD_PROJECT" ]; then \
		echo "Error: GOOGLE_CLOUD_PROJECT environment variable not set"; \
		exit 1; \
	fi
	@if [ -z "$$GOOGLE_APPLICATION_CREDENTIALS" ] && [ ! -f "$$HOME/.config/gcloud/application_default_credentials.json" ]; then \
		echo "Error: GCP credentials not found. Run 'gcloud auth application-default login' or set GOOGLE_APPLICATION_CREDENTIALS"; \
		exit 1; \
	fi
	uv run custodian validate $(POLICY_FILE)
	uv run custodian run --dryrun -s ./tmp/output $(POLICY_FILE)

run-gcp-policy:
	@echo "Running GCP policy (LIVE)..."
	@read -p "This will execute actions on GCP resources. Continue? [y/N] " confirm && [ "$$confirm" = "y" ]
	uv run custodian run -s ./tmp/output $(POLICY_FILE)

.PHONY: test-gcp-policy run-gcp-policy
