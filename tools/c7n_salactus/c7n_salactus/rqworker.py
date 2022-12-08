# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
rq worker customizations
 - dont fork per job
 - use compressed msg pack messages (less mem in queue)
"""
import datetime
import msgpack
import cPickle
import logging

from lz4.frame import compress, decompress
from rq.worker import Worker
from rq import job

PackDate_ExtType = 42
PackObj_ExtType = 43

job_default_load = job.loads

log = logging.getLogger('salactus')
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
log.addHandler(handler)
log.setLevel(logging.INFO)


def decode_ext(code, data):
    if code == PackDate_ExtType:
        values = msgpack.unpackb(data)
        return datetime.datetime(*values)
    elif code == PackObj_ExtType:
        return cPickle.loads(data)
    return msgpack.ExtType(code, data)


def encode_ext(obj):
    if isinstance(obj, datetime.datetime):
        components = (obj.year, obj.month, obj.day, obj.hour, obj.minute,
                      obj.second, obj.microsecond)
        data = msgpack.ExtType(PackDate_ExtType, msgpack.packb(components))
        return data
    return msgpack.ExtType(
        PackObj_ExtType,
        cPickle.dumps(obj, protocol=cPickle.HIGHEST_PROTOCOL))


def dumps(o):
    return compress(
        msgpack.packb(o, default=encode_ext, use_bin_type=True))


def loads(s):
    try:
        return msgpack.unpackb(
            decompress(s), ext_hook=decode_ext, encoding='utf-8')
    except Exception:
        # we queue work occassionally from lambdas or other systems not using
        # the worker class
        return job_default_load(s)


job.dumps = dumps
job.loads = loads


class SalactusWorker(Worker):
    """Get rid of process boundary, maintain worker status.

    We rely on supervisord for process supervision, and we want
    to be able to cache sts sessions per process to avoid role
    assume storms.
    """

    def execute_job(self, job, queue):
        self.set_state('busy')
        self.perform_job(job, queue)
        self.set_state('idle')
