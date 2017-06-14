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
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('directory')
class Directory(QueryResourceManager):

    class resource_type(object):
        service = "ds"
        enum_spec = ("describe_directories", "DirectoryDescriptions", None)
        name = "Name"
        id = "DirectoryId"
        dimension = None


@resources.register('cloud-directory')
class CloudDirectory(QueryResourceManager):

    class resource_type(object):
        service = "clouddirectory"
        enum_spec = ("list_directories", "Directories", None)
        id = "DirectoryArn"
        name = "Name"
        dimension = None
