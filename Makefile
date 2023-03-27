SHELL := /bin/bash
SELF_MAKE := $(lastword $(MAKEFILE_LIST))

PKG_REPO = testpypi
PKG_INCREMENT := patch
PKG_SET := tools/c7n_gcp tools/c7n_kube tools/c7n_openstack tools/c7n_mailer tools/c7n_logexporter tools/c7n_policystream tools/c7n_trailcreator tools/c7n_org tools/c7n_sphinxext tools/c7n_terraform tools/c7n_awscc tools/c7n_tencentcloud tools/c7n_azure

FMT_SET := tools/c7n_left

PLATFORM_ARCH := $(shell python3 -c "import platform; print(platform.machine())")
PLATFORM_OS := $(shell python3 -c "import platform; print(platform.system())")
PY_VERSION := $(shell python3 -c "import sys; print('%s.%s' % (sys.version_info.major, sys.version_info.minor))")

COVERAGE_TYPE := html
ARGS :=
IMAGE := c7n
IMAGE_TAG := latest

ifneq "$(findstring $(PLATFORM_OS), Linux Darwin)" ""
  ifneq "$(findstring $(PY_VERSION), 3.10)" ""
    PKG_SET := tools/c7n_left $(PKG_SET)
  endif
  ifneq "$(findstring $(PY_VERSION), 3.11)" ""
    PKG_SET := tools/c7n_left $(PKG_SET)
  endif
endif


###
# Common developer targets

install:
	@if [[ -z "$(VIRTUAL_ENV)" ]]; then echo "Create and Activate VirtualEnv First, ie. python3 -m venv .venv && source .venv/bin/activate"; exit 1; fi
	poetry install
	for pkg in $(PKG_SET); do echo "Install $$pkg" && cd $$pkg && poetry install --all-extras && cd ../..; done

.PHONY: test

test:
	. $(PWD)/test.env && poetry run pytest -n auto tests tools $(ARGS)

test-coverage:
	. $(PWD)/test.env && poetry run pytest -n auto \
            --cov-report $(COVERAGE_TYPE) \
            --cov c7n \
            --cov tools/c7n_azure/c7n_azure \
            --cov tools/c7n_gcp/c7n_gcp \
            --cov tools/c7n_kube/c7n_kube \
            --cov tools/c7n_left/c7n_left \
            --cov tools/c7n_terraform/c7n_terraform \
            --cov tools/c7n_mailer/c7n_mailer \
            --cov tools/c7n_policystream/c7n_policystream \
            --cov tools/c7n_tencentcloud/c7n_tencentcloud \
            tests tools $(ARGS)

test-functional:
# note this will provision real resources in a cloud environment
	C7N_FUNCTIONAL=yes AWS_DEFAULT_REGION=us-east-2 pytest tests -m functional $(ARGS)

sphinx:
	make -f docs/Makefile.sphinx html

lint:
	ruff c7n tests tools
	black --check $(FMT_SET)
	type -P terraform && terraform fmt -check -recursive .

format:
	black $(FMT_SET)
	ruff --fix c7n tests tools
	type -P terraform && terraform fmt -recursive .

clean:
	make -f docs/Makefile.sphinx clean
	rm -rf .tox .Python bin include lib pip-selfcheck.json
	@$(MAKE) -f $(SELF_MAKE) pkg-clean

image:
	docker build -f docker/$(IMAGE) -t $(IMAGE):$(IMAGE_TAG) .

gen-docker:
	python tools/dev/dockerpkg.py generate
###
# Package Management Targets
# - primarily used to help drive frozen releases and dependency upgrades

pkg-rebase:
	rm -f poetry.lock
	for pkg in $(PKG_SET); do cd $$pkg && echo $$pkg && rm -f poetry.lock && cd ../..; done
	@$(MAKE) -f $(SELF_MAKE) pkg-update
	git add poetry.lock
	for pkg in $(PKG_SET); do cd $$pkg && echo $$pkg && git add poetry.lock && cd ../..; done

pkg-clean:
	rm -f dist/*
	for pkg in $(PKG_SET); do cd $$pkg && rm -f dist/* && cd ../..; done

	rm -Rf build/*
	for pkg in $(PKG_SET); do cd $$pkg && rm -Rf build/* && cd ../..; done

pkg-update:
	poetry update
	for pkg in $(PKG_SET); do cd $$pkg && echo $$pkg && poetry update && cd ../..; done

pkg-show-update:
	poetry show -o
	for pkg in $(PKG_SET); do cd $$pkg && echo $$pkg && poetry show -o && cd ../..; done

pkg-increment:
# increment versions
	poetry version $(PKG_INCREMENT)
	for pkg in $(PKG_SET); do cd $$pkg && poetry version $(PKG_INCREMENT) && cd ../..; done
	poetry run python tools/dev/poetrypkg.py gen-version-file -p . -f c7n/version.py

pkg-build-wheel:
# requires plugin installation -> poetry self add poetry-plugin-freeze
	@$(MAKE) -f $(SELF_MAKE) pkg-clean

	poetry build --format wheel
	for pkg in $(PKG_SET); do cd $$pkg && poetry build --format wheel && cd ../..; done

	poetry freeze-wheel

	twine check --strict dist/*
	for pkg in $(PKG_SET); do cd $$pkg && twine check --strict dist/* && cd ../..; done

pkg-publish-wheel:
# upload to test pypi
	poetry publish -r $(PKG_REPO)
	for pkg in $(PKG_SET); do cd $$pkg && poetry publish -r $(PKG_REPO) && cd ../..; done


###
# Static analyzers

analyzer-bandit:
	bandit -i -s B101,B311 \
	-r tools/c7n_azure/c7n_azure \
	 tools/c7n_gcp/c7n_gcp \
	 tools/c7n_terraform/c7n_terraform \
	 tools/c7n_guardian/c7n_guardian \
	 tools/c7n_org/c7n_org \
	 tools/c7n_mailer/c7n_mailer \
	 tools/c7n_policystream/policystream.py \
	 tools/c7n_trailcreator/c7n_trailcreator \
	 c7n


analyzer-semgrep:
	semgrep --error --verbose --config p/security-audit \
	 tools/c7n_azure/c7n_azure \
	 tools/c7n_gcp/c7n_gcp \
	 tools/c7n_terraform/c7n_terraform \
	 tools/c7n_guardian/c7n_guardian \
	 tools/c7n_org/c7n_org \
	 tools/c7n_mailer/c7n_mailer \
	 tools/c7n_policystream/policystream.py \
	 tools/c7n_trailcreator/c7n_trailcreator \
	 c7n
