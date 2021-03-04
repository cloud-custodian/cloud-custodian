# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Provide basic caching services to avoid extraneous queries over
multiple policies on the same resource type.
"""
import pickle

import os
import logging
import time

log = logging.getLogger('custodian.cache')

CACHE_NOTIFY = False


def factory(config):

    global CACHE_NOTIFY

    if not config:
        return NullCache(None)

    if not config.cache or not config.cache_period:
        if not CACHE_NOTIFY:
            log.debug("Disabling cache")
            CACHE_NOTIFY = True
        return NullCache(config)
    elif config.cache == 'memory':
        if not CACHE_NOTIFY:
            log.debug("Using in-memory cache")
            CACHE_NOTIFY = True
        return InMemoryCache()

    return FileCacheManager(config)


class NullCache:

    def __init__(self, config):
        self.config = config

    def load(self):
        return False

    def get(self, key):
        pass

    def save(self, key, data):
        pass

    def size(self):
        return 0


class InMemoryCache:
    # Running in a temporary environment, so keep as a cache.

    __shared_state = {}

    def __init__(self):
        self.data = self.__shared_state

    def load(self):
        return True

    def get(self, key):
        return self.data.get(pickle.dumps(key))

    def save(self, key, data):
        self.data[pickle.dumps(key)] = data

    def size(self):
        return sum(map(len, self.data.values()))


class FileCacheManager:

    def __init__(self, config):
        self.config = config
        self.cache_period = config.cache_period
        self.cache_path = os.path.abspath(
            os.path.expanduser(
                os.path.expandvars(
                    config.cache)))
        self.data = {}

    def get(self, key):
        k = pickle.dumps(key)
        return self.data.get(k)

    def load(self):
        if self.data:
            return True
        if os.path.isfile(self.cache_path):
            if (time.time() - os.stat(self.cache_path).st_mtime >
                    self.config.cache_period * 60):
                return False
            with open(self.cache_path, 'rb') as fh:
                try:
                    self.data = pickle.load(fh)
                except EOFError:
                    return False
            log.debug("Using cache file %s" % self.cache_path)
            return True

    def save(self, key, data):
        try:
            with open(self.cache_path, 'wb') as fh:
                self.data[pickle.dumps(key)] = data
                pickle.dump(self.data, fh, protocol=2)
        except Exception as e:
            log.warning("Could not save cache %s err: %s" % (
                self.cache_path, e))
            if not os.path.exists(self.cache_path):
                directory = os.path.dirname(self.cache_path)
                log.info('Generating Cache directory: %s.' % directory)
                try:
                    os.makedirs(directory)
                except Exception as e:
                    log.warning("Could not create directory: %s err: %s" % (
                        directory, e))

    def size(self):
        return os.path.exists(self.cache_path) and os.path.getsize(self.cache_path) or 0
