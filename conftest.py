# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
try:
    import freezegun
except ImportError:  # noqa
    # docker tests run with minimal deps
    freezegun = None

if freezegun is not None:
    # The kubernetes client (>=37) loads its pydantic models lazily on
    # attribute access. When freezegun starts, it reads all attributes of
    # each loaded module, so it imports these models while datetime is
    # patched. The pydantic model build then fails, freezegun stops half
    # way, and the patched datetime leaks into other tests.
    freezegun.configure(extend_ignore_list=["kubernetes"])
