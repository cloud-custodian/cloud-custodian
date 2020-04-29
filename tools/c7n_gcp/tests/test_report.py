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


from c7n.resources import load_resources
from gcp_common import BaseTest

from c7n_gcp.provider import GoogleCloud


class ReportMetadataTests(BaseTest):

    def test_report_metadata(self):
        load_resources(('gcp.*',))

        missing = set()
        for k, v in GoogleCloud.resources.items():
            if (not v.resource_type.id or
                not v.resource_type.name or
                    not v.resource_type.default_report_fields):
                missing.add("%s~%s" % (k, v))

        if missing:
            raise AssertionError("Missing report metadata on \n %s" % (' \n'.join(sorted(missing))))
