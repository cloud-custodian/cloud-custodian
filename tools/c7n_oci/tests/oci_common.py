import re
import time
from enum import Enum

import oci
from c7n_oci.query import DescribeService

from c7n.config import Config
from c7n.schema import generate
from c7n.testing import C7N_FUNCTIONAL, CustodianTestCore


class OciBaseTest(CustodianTestCore):

    def addCleanup(self, func, *args, **kw):
        pass

    custodian_schema = generate()

    def load_policy(self, data, *args, **kw):
        if "config" not in kw:
            config = Config.empty(**{
                "region": kw.pop("region", "us-ashburn-1"),
                "account_id": kw.pop('account_id', "1"),
                "output_dir": "null://",
                "log_group": "null://",
                "cache": False,
            })
            kw['config'] = config
        return super().load_policy(data, *args, **kw)

    def get_defined_tag(self, test_type):
        return {'cloud-custodian-test': {'mark-for-resize': 'true' if test_type == 'add_tag' else 'false'}}

    def get_defined_tag_value(self, tag_details):
        return tag_details['cloud-custodian-test']['mark-for-resize']

    def get_defined_tag_key(self):
        return 'defined_tags."cloud-custodian-test"."mark-for-resize"'

    def wait_for_resource_search_sync(self, duration=15):
        if C7N_FUNCTIONAL:
            time.sleep(duration)

    def get_resources(self, policy, compartment_id, id=None, name=None, **kwargs):
        params = {'compartment_id': compartment_id}
        for key, value in kwargs.items():
            params[key] = value

        describe_service = DescribeService(policy.resource_manager)
        resources = describe_service.get_resources(None, params)
        if id:
            return [oci.util.to_dict(resource) for resource in resources if resource.id == id]
        elif name:
            return [oci.util.to_dict(resource) for resource in resources if resource.name == name]
        else:
            return [oci.util.to_dict(resource) for resource in resources]


## common functions
def replace_ocid(data):
    return re.sub(r'\.oc1\..*?"', '.oc1..<unique_ID>"', data)

def replace_email(data):
    return re.sub(r'"[^"]+@oracle\.com"', '"user@example.com"', data)

### ENUM ###
class Scope(Enum):
    CLASS = 'class'
    SESSION = 'session'
    FUNCTION = 'function'


class Module(Enum):
    COMPUTE = 'compute'
    OBJECT_STORAGE = 'object_storage'
    VCN = 'vcn'
    ZONE = 'zone'
    SUBNET = 'subnet'
    IDENTITY_GROUP = 'identity_group'
    IDENTITY_COMPARTMENT = 'identity_compartment'
    IDENTITY_USER = 'identity_user'


class Resource(Enum):
    COMPUTE = 'oci.instance'
    BUCKET = 'oci.bucket'
    VCN = 'oci.vcn'
    ZONE = 'oci.zone'
    SUBNET = 'oci.subnet'
    COMPARTMENT = 'oci.compartment'
    GROUP = 'oci.group'
    USER = 'oci.user'
