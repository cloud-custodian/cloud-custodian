# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources
from c7n.filters.offhours import OffHour, OnHour


@resources.register('cron-job')
class CronJob(QueryResourceManager):

    class resource_type(TypeInfo):
        group = 'Batch'
        version = 'V1'
        patch = 'patch_namespaced_cron_job'
        delete = 'delete_namespaced_cron_job'
        enum_spec = ('list_cron_job_for_all_namespaces', 'items', None)

CronJob.filter_registry.register('offhour', OffHour)
CronJob.filter_registry.register('onhour', OnHour)
