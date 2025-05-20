# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
SHELL := /bin/bash
SELF_MAKE := $(lastword $(MAKEFILE_LIST))

PKG_REPO = testpypi
PKG_INCREMENT := patch
PKG_SET := tools/c7n_gcp tools/c7n_kube tools/c7n_openstack tools/c7n_mailer tools/c7n_logexporter tools/c7n_policystream tools/c7n_trailcreator tools/c7n_org tools/c7n_sphinxext tools/c7n_awscc tools/c7n_tencentcloud tools/c7n_azure tools/c7n_oci tools/c7n_terraform

FMT_SET := tools/c7n_left tools/c7n_mailer tools/c7n_oci tools/c7n_kube tools/c7n_awscc

PLATFORM_ARCH := $(shell python3 -c "import platform; print(platform.machine())")
PLATFORM_OS := $(shell python3 -c "import platform; print(platform.system())")
PY_VERSION := $(shell python3 -c "import sys; print('%s.%s' % (sys.version_info.major, sys.version_info.minor))")

COVERAGE_TYPE := html
ARGS :=
IMAGE := c7n
IMAGE_TAG := latest

# we distribute tfparse binary wheels for 3.10+
ifneq "$(findstring 3.1, $(PY_VERSION))" ""
    PKG_SET := tools/c7n_left $(PKG_SET)
endif


###
# Common developer targets

install:
# extras are for c7n_mailer, separate lint from dev for ci
	uv sync --all-packages \
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
	type -P terraform && terraform fmt -check -recursive .

format:
	uv run black $(FMT_SET)
	uv run ruff check --fix c7n tests tools
	type -P terraform && terraform fmt -recursive .

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

pkg-rebase:
	rm -f uv.lock
	@$(MAKE) -f $(SELF_MAKE) pkg-update
	git add uv.lock

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
	uv version $(PKG_INCREMENT)
	for pkg in $(PKG_SET); do cd $$pkg && uv version $(PKG_INCREMENT) && cd ../..; done
	uv run tools/dev/devpkg.py gen-version-file -p . -f c7n/version.py

pkg-build-wheel:
	@$(MAKE) -f $(SELF_MAKE) pkg-clean
	uv build --all-packages --wheel
	uv run tools/dev/freezeuvwheel dist uv.lock
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
	cd tools/c7n_left/scripts && python get_taggable.py \
		--module-path taggable_providers/latest \
		--module-path taggable_providers/azurerm-previous \
		--output ../c7n_left/data/taggable.json
# aws data sets
	python tools/dev/cfntypedb.py -f tests/data/cfn-types.json
	python tools/dev/updatearnref.py > tests/data/arn-types.json
	python tools/dev/iamdb.py -f tests/data/iam-actions.json
# gcp data sets
	python tools/dev/gcpiamdb.py -f tools/c7n_gcp/tests/data/iam-permissions.json
	python tools/dev/gcpregion.py -f tools/c7n_gcp/c7n_gcp/regions.json

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
