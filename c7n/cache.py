# Copyright 2016 Capital One Services, LLC
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
"""Provide basic caching services to avoid extraneous queries over
multiple policies on the same resource type.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import cPickle

import os
import logging
import time

log = logging.getLogger('custodian.cache')


def factory(config):
    if not config:
        return NullCache(None)

    if not config.cache or not config.cache_period:
        log.debug("Disabling cache")
        return NullCache(config)

    return FileCacheManager(config)


class NullCache(object):

    def __init__(self, config):
        self.config = config

    def load(self):
        return False

    def get(self, key):
        pass

    def save(self, key, data):
        pass


class FileCacheManager(object):

    def __init__(self, config):
        self.config = config
        self.cache_period = config.cache_period
        self.cache_path = os.path.abspath(
            os.path.expanduser(
                os.path.expandvars(
                    config.cache)))
        self.data = {}

    def get(self, key):
        k = cPickle.dumps(key)
        return self.data.get(k)

    def load(self):
        if self.data:
            return True
        if os.path.isfile(self.cache_path):
            if (time.time() - os.stat(self.cache_path).st_mtime >
                    self.config.cache_period * 60):
                return False
            with open(self.cache_path) as fh:
                try:
                    self.data = cPickle.load(fh)
                except EOFError:
                    return False
            log.debug("Using cache file %s" % self.cache_path)
            return True

    def save(self, key, data):
        try:
            with open(self.cache_path, 'w') as fh:
                self.data[cPickle.dumps(key)] = data
                cPickle.dump(self.data, fh, protocol=2)
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
