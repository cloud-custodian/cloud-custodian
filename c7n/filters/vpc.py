from .core import Filter
from c7n.utils import local_session


class DefaultVpcBase(Filter):

    vpcs = None
    default_vpc = None

    def match(self, vpc_id):
        if self.default_vpc is None:
            self.log.debug("querying default vpc %s" % vpc_id)
            client = local_session(self.manager.session_factory).client('ec2')
            vpcs = [v['VpcId'] for v
                    in client.describe_vpcs(VpcIds=[vpc_id])['Vpcs']
                    if v['IsDefault']]
            if not vpcs:
                self.default_vpc = ""
            else:
                self.default_vpc = vpcs.pop()
        return vpc_id == self.default_vpc and True or False
