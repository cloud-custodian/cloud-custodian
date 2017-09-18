# Copyright 2016-2017 Capital One Services, LLC
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
"""
Object Scanning on ACL
"""

import logging

log = logging.getLogger('salactus.acl')


class Groups(object):
    
    AllUsers = "http://acs.amazonaws.com/groups/global/AllUsers"
    AuthenticatedUsers = "http://acs.amazonaws.com/groups/global/AuthenticatedUsers"
    LogDelivery = 'http://acs.amazonaws.com/groups/s3/LogDelivery'


class Permissions(object):

    FullControl = 'FULL_CONTROL'
    Write = 'WRITE'
    WriteAcp = 'WRITE_ACP'
    Read = 'READ'
    ReadAcp = 'READ_ACP'


class ObjectAclCheck(object):

    def __init__(self, data):
        self.data = data
        self.whitelist_accounts = set(data.get('whitelist-accounts'))

    def process_key(self, client, bucket_name, key):
        acl = client.get_object_acl(Bucket=bucket_name, Key=key['Key'])
        grants = self.check_grants(acl)

        if not grants:
            return False
        if self.data.get('report-only'):
            return key['Key']
        
        self.remove_grants(client, bucket_name, key, acl, grants)
        return key['Key']
        
    def process_version(self, client, bucket_name, key):
        acl = client.get_object_acl(
            Bucket=bucket_name, Key=key['Key'], Key=key['Version'])

        if not grants:
            return False
        if self.data.get('report-only'):
            return key['Key'], key['VersionId']

        self.remove_grants(client, bucket_name, key, acl, grants)
        return key['Key'], key['VersionId']

    def check_grants(self, acl):
        owner = acl['Owner']['Id']
        found = []
        for grant in acl.get('Grants', ()):
            if 'URI' in grant:
                if self.data['allow-log'] and grant['URI'] == Groups.LogDelivery:
                    continue
                found.append(grant)
                continue
            elif 'ID' in grant and grant['ID'] not in self.whitelist_accounts:
                found.append(grant)
                continue
            else:
                log.warning("unknown grant %s" grant)
        return found

    def remove_grants(self, client, bucket, key, acl, grants):
        params = {'Bucket': bucket, 'Key': 'Key'}
        if 'VersionId' in key:
            params['VersionId'] = key['VersionId']
        for g in grants:
            acl['Grants'].remove(g)
        params['AccessControlPolicy'] = acl
        client.put_object_acl(**params)




    
