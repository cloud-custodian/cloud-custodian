# Copyright 2017-2018 Capital One Services, LLC
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
from dateutil.parser import parse
from aliyunsdkecs.request.v20140526.DeleteDiskRequest import DeleteDiskRequest
from aliyunsdkecs.request.v20140526.DescribeDisksRequest import DescribeDisksRequest
from aliyunsdkecs.request.v20140526.DescribeDiskMonitorDataRequest import DescribeDiskMonitorDataRequest
from c7n_aliyun.actions import MethodAction
from c7n_aliyun.filters.filter import AliyunDiskFilter, MetricsFilter
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo

from c7n.utils import type_schema


@resources.register('disk')
class Disk(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'disk'
        enum_spec = (None, 'Disks.Disk', None)
        id = 'DiskId'

    def get_request(self):
        request = DescribeDisksRequest()
        return request

@Disk.filter_registry.register('encrypted')
class AliyunDiskFilter(AliyunDiskFilter):
    """Filters

       :Example:

       .. code-block:: yaml

           policies:
             - name: aliyun-encrypted-disk
               resource: aliyun.disk
               filters:
                 - type: encrypted
                   value: false
    """
    # 云盘是否加密。
    # 默认值：false
    schema = type_schema(
        'encrypted',
        **{'value': {'type': 'boolean'}})

    def get_request(self, i):
        encrypted = self.data.get('type', '')
        if i.get('Encrypted', '').lower() != str(encrypted).lower():
            return False
        return i

@Disk.filter_registry.register('unused')
class AliyunDiskFilter(AliyunDiskFilter):
    """Filters

       :Example:

       .. code-block:: yaml

           policies:
             - name: aliyun-orphaned-disk
               resource: aliyun.disk
               filters:
                 - type: unused
    """
    # Associating：绑定中。
    # Unassociating：解绑中。
    # InUse：已分配。
    # Available：可用。
    schema = type_schema('Available')

    def get_request(self, i):
        if i.get('Status', '') != 'Available':
            return False
        return i

@Disk.filter_registry.register('metrics')
class MetricsDiskFilter(MetricsFilter):

    """
          policies:
            - name: aliyun-disk
              resource: aliyun.disk
              filters:
                - type: unused
                - type: metrics
                  name: IOPSTotal
                  period: 600
                  startTime: '2020-11-02T08:00:00Z'
                  endTime: '2020-11-04T08:00:00Z'
                  statistics: Average
                  value: 0
                  op: eq
    """
    # 系统盘I/O读写总操作，单位：次/s。IOPSTotal
    # 系统盘读写总带宽，单位：Byte/s。BPSTotal
    def get_request(self, disk):
        request = DescribeDiskMonitorDataRequest()
        request.set_StartTime(datetime.datetime.strptime(str(self.start), '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%dT%H:%M:%SZ'))
        request.set_EndTime(datetime.datetime.strptime(str(self.end), '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%dT%H:%M:%SZ'))
        request.set_DiskId(disk["DiskId"])
        request.set_Period(self.period)
        request.set_accept_format('json')
        return request

# @Disk.action_registry.register('delete')
# class DiskDelete(MethodAction):
#
#     schema = type_schema('delete')
#     method_spec = {'op': 'delete'}
#     attr_filter = ('Status', ('Available', ))
#
#     def get_request(self, disk):
#         request = DeleteDiskRequest()
#         request.set_DiskId(disk['DiskId'])
#         request.set_accept_format('json')
#         return request