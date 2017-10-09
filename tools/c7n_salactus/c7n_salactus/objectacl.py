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

    def __init__(self, data, record_users=False):
        self.data = data
        self.whitelist_accounts = set(data.get('whitelist-accounts', ()))
        self.record_users = record_users

    def process_key(self, client, bucket_name, key):
        acl = client.get_object_acl(Bucket=bucket_name, Key=key['Key'])
        acl.pop('ResponseMetadata')
        grants = self.check_grants(acl)

        if not grants:
            return False
        if self.data.get('report-only'):
            return {'key': key['Key'], 'grants': grants}
        
        self.remove_grants(client, bucket_name, key, acl, grants)
        return {'key': key['Key'], 'grants': grants}
        
    def process_version(self, client, bucket_name, key):
        acl = client.get_object_acl(
            Bucket=bucket_name, Key=key['Key'], VersionId=key['VersionId'])
        acl.pop('ResponseMetadata')
        grants = self.check_grants(acl)

        if not grants:
            return False
        if self.data.get('report-only'):
            return {'key': key['Key'], 'version': key['VersionId'], 'grants': grants}

        self.remove_grants(client, bucket_name, key, acl, grants)
        return {'key': key['Key'], 'version': key['VersionId'], 'grants': grants}

    def record_users(self, acl):
        users = {}
        users[acl['Owner']['DisplayName']] = acl['Owner']['ID']
        for g in acl.get('Grants'):
            grantee = g['Grantee']
            if 'ID' in grantee:
                users[grantee['DisplayName']] = grantee['ID']
        from c7n_salactus.worker import connection
        connection.hmset('bucket-user', users)

    def check_grants(self, acl):
        owner = acl['Owner']['ID']
        found = []
        for grant in acl.get('Grants', ()):
            grantee = grant['Grantee']
            if 'ID' in grantee and grantee['ID'] == owner:
                continue
            elif 'URI' in grantee:
                if self.data['allow-log'] and grantee['URI'] == Groups.LogDelivery:
                    continue
                found.append(grant)
            elif 'ID' in grantee:
                if '*' in self.whitelist_accounts:
                   continue
                if grantee['ID'] not in self.whitelist_accounts:
                    found.append(grant)
            else:
                log.warning("unknown grant %s", grant)
        return found

    def remove_grants(self, client, bucket, key, acl, grants):
        params = {'Bucket': bucket, 'Key': 'Key'}

        if 'VersionId' in key:
            params['VersionId'] = key['VersionId']
        for g in grants:
            acl['Grants'].remove(g)
        params['AccessControlPolicy'] = acl
        client.put_object_acl(**params)




    
