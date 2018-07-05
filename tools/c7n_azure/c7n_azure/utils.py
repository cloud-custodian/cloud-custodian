# Copyright 2018 Capital One Services, LLC
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
import datetime


class ResourceIdParser(object):

    @staticmethod
    def get_namespace(resource_id):
        return resource_id.split('/')[6]

    @staticmethod
    def get_resource_group(resource_id):
        return resource_id.split('/')[4]

    @staticmethod
    def get_resource_type(resource_id):
        return resource_id.split('/')[7]

    @staticmethod
    def get_resource_name(resource_id):
        return resource_id.split('/')[8]


def utcnow():
    """The datetime object for the current time in UTC
    """
    return datetime.datetime.utcnow()


def now(tz=None):
    """The datetime object for the current time in UTC
    """
    return datetime.datetime.now(tz=tz)


class Math(object):

    @staticmethod
    def mean(numbers):
        clean_numbers = [e for e in numbers if e is not None]
        return float(sum(clean_numbers)) / max(len(clean_numbers), 1)

    @staticmethod
    def sum(numbers):
        clean_numbers = [e for e in numbers if e is not None]
        return float(sum(clean_numbers))
