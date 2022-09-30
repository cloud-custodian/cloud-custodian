# Copyright 2020 Kapil Thangavelu
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib

import portalocker
from py.path import local

PollInterval = 5
LockTimeout = 300


@contextlib.contextmanager
def lock_create(file_path, timeout=LockTimeout, interval=PollInterval):
    """Context manager for file creation with file locking

    return a tuple either
        - (false, file_content)
        - (true, file_handle)
    """
    fp = local(file_path)
    if fp.exists():
        yield False, fp.read_text("utf8")
        return
    with portalocker.Lock(
        str(fp.dirpath() / (fp.basename + ".lock")),
        timeout=timeout,
        check_interval=interval,
    ):
        if fp.exists():
            yield False, fp.read_text("utf8")
            return
        with portalocker.open_atomic(str(fp)) as fh:
            yield True, fh
            fh.flush()


@contextlib.contextmanager
def lock_delete(file_path, timeout=LockTimeout, interval=PollInterval):
    """Context manager for file delete with file locking

    Returns boolean
      - False if file didn't exist
      - True if file will be deleted
    """
    pointer = local(file_path)
    if not pointer.exists():
        yield False
        return
    with portalocker.Lock(
        str(pointer.dirpath() / (pointer.basename + ".lock")),
        timeout=timeout,
        check_interval=interval,
    ):
        if not pointer.exists():
            yield False
            return
        yield True
        pointer.remove()
