import logging
from c7n.utils import local_session
from c7n_azure.session import Session
from azure.mgmt.monitor import MonitorManagementClient


class AutoScaleUtilities(object):
    log = logging.getLogger('custodian.azure.autoscale_utils')

    def __init__(self, app_service_plan, autoscale):
        self._app_service_plan = app_service_plan
        self._enable_autoscale= autoscale['enable_auto_scale']
        self._min_capacity = autoscale['min_capacity']
        self._max_capacity=autoscale['max_capacity']
        self._default_capacity=autoscale['default_capacity']

    def _validate_values(self):
        if isinstance(self._min_capacity,int):
            self._min_capacity= str(self._min_capacity)
        if isinstance(self._max_capacity, int):
            self._min_capacity = str(self._min_capacity)
        if isinstance(self._default_capacity, int):
            self._min_capacity = str(self._min_capacity)

    @staticmethod
    def _initialize_autoscale_client():
        session = local_session(Session)
        auto_scale_client = MonitorManagementClient(session.credentials, session.subscription_id)
        return auto_scale_client

    def _initialize_parameters(self):
        self._validate_values()
        auto_scale_parameters = {
            "location": self._app_service_plan.location,
            "targetResourceUri": self._app_service_plan.id,
            "properties": {
                "enabled": self._enable_autoscale,
                "profiles": [
                    {
                        "name": "Auto created scale condition",
                        "capacity": {
                            "minimum": self._min_capacity,
                            "maximum": self._max_capacity,
                            "default": self._default_capacity
                        },
                        "rules": []
                    }
                ]
            }
        }
        return auto_scale_parameters

    def deploy_auto_scale(self, app_resource_group_name):
        self._initialize_autoscale_client().autoscale_settings.create_or_update(app_resource_group_name, "autoscale",
                                                                            self._initialize_parameters())
