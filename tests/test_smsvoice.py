# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


def _tag(resource, key='c7n-test'):
    return {t['Key']: t['Value'] for t in resource.get('Tags', [])}.get(key)


class SmsVoicePhoneNumberTest(BaseTest):

    def test_sms_voice_phone_number_query(self):
        session_factory = self.replay_flight_data('test_sms_voice_phone_number_query')
        p = self.load_policy(
            {'name': 'sms-voice-phone-number-query',
             'resource': 'aws.sms-voice-phone-number',
             'filters': [{'tag:c7n-test': 'query'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['PhoneNumberArn'].startswith('arn:aws:sms-voice:'))
        self.assertEqual(
            p.resource_manager.get_arns(resources), [resources[0]['PhoneNumberArn']])

    def test_sms_voice_phone_number_cross_account(self):
        session_factory = self.replay_flight_data(
            'test_sms_voice_phone_number_cross_account')
        p = self.load_policy(
            {'name': 'sms-voice-phone-number-cross-account',
             'resource': 'aws.sms-voice-phone-number',
             'filters': [{'type': 'cross-account'}]},
            session_factory=session_factory)
        resources = p.run()
        # one number shared with a foreign account, one without a resource policy
        self.assertEqual(len(resources), 1)
        self.assertEqual(_tag(resources[0]), 'shared')
        self.assertTrue(resources[0]['c7n:Policy'])
        self.assertTrue(resources[0]['CrossAccountViolations'])

    def test_sms_voice_phone_number_pool_registration(self):
        session_factory = self.replay_flight_data(
            'test_sms_voice_phone_number_pool_registration')
        p = self.load_policy(
            {'name': 'sms-voice-prod-pool-phone-number-registration',
             'resource': 'aws.sms-voice-phone-number',
             'filters': [
                 {'type': 'pool', 'key': 'tag:Environment', 'value': 'prod'},
                 {'not': [
                     {'type': 'registration',
                      'key': 'RegistrationStatus',
                      'value': 'COMPLETE'}]}]},
            session_factory=session_factory)
        resources = p.run()
        # prod pool holds one number with a non-COMPLETE registration and one
        # with a COMPLETE registration; a third number sits in a non-prod pool
        self.assertEqual(len(resources), 1)
        self.assertEqual(_tag(resources[0]), 'unregistered')
        self.assertEqual(resources[0]['c7n:PoolIds'], [resources[0]['PoolId']])

    def test_sms_voice_phone_number_tag(self):
        session_factory = self.replay_flight_data('test_sms_voice_phone_number_tag')
        p = self.load_policy(
            {'name': 'sms-voice-phone-number-tag',
             'resource': 'aws.sms-voice-phone-number',
             'filters': [{'tag:c7n-test': 'tag'}],
             'actions': [{'type': 'tag', 'key': 'Owner', 'value': 'c7n'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('pinpoint-sms-voice-v2')
        tags = client.list_tags_for_resource(
            ResourceArn=resources[0]['PhoneNumberArn'])['Tags']
        self.assertIn({'Key': 'Owner', 'Value': 'c7n'}, tags)

    def test_sms_voice_phone_number_remove_tag(self):
        session_factory = self.replay_flight_data(
            'test_sms_voice_phone_number_remove_tag')
        p = self.load_policy(
            {'name': 'sms-voice-phone-number-remove-tag',
             'resource': 'aws.sms-voice-phone-number',
             'filters': [{'tag:Owner': 'c7n'}],
             'actions': [{'type': 'remove-tag', 'tags': ['Owner']}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('pinpoint-sms-voice-v2')
        tags = client.list_tags_for_resource(
            ResourceArn=resources[0]['PhoneNumberArn'])['Tags']
        self.assertNotIn('Owner', [t['Key'] for t in tags])


class SmsVoiceSenderIdTest(BaseTest):

    def test_sms_voice_sender_id_query(self):
        session_factory = self.replay_flight_data('test_sms_voice_sender_id_query')
        p = self.load_policy(
            {'name': 'sms-voice-sender-id-query',
             'resource': 'aws.sms-voice-sender-id',
             'filters': [{'tag:c7n-test': 'query'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            p.resource_manager.get_arns(resources), [resources[0]['SenderIdArn']])

    def test_sms_voice_sender_id_cross_account(self):
        session_factory = self.replay_flight_data(
            'test_sms_voice_sender_id_cross_account')
        p = self.load_policy(
            {'name': 'sms-voice-sender-id-cross-account',
             'resource': 'aws.sms-voice-sender-id',
             'filters': [{'type': 'cross-account'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(_tag(resources[0]), 'shared')

    def test_sms_voice_sender_id_pool(self):
        session_factory = self.replay_flight_data('test_sms_voice_sender_id_pool')
        p = self.load_policy(
            {'name': 'sms-voice-sender-id-prod-pool',
             'resource': 'aws.sms-voice-sender-id',
             'filters': [{'type': 'pool', 'key': 'tag:Environment', 'value': 'prod'}]},
            session_factory=session_factory)
        resources = p.run()
        # one sender id in a prod-tagged pool, one in no pool
        self.assertEqual(len(resources), 1)
        self.assertEqual(_tag(resources[0]), 'prod-pool')
        self.assertEqual(len(resources[0]['c7n:PoolMembership']), 1)
        self.assertEqual(resources[0]['c7n:PoolIds'], resources[0]['c7n:PoolMembership'])


class SmsVoicePoolTest(BaseTest):

    def test_sms_voice_pool_query(self):
        session_factory = self.replay_flight_data('test_sms_voice_pool_query')
        p = self.load_policy(
            {'name': 'sms-voice-pool-query',
             'resource': 'aws.sms-voice-pool',
             'filters': [{'tag:c7n-test': 'query'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            p.resource_manager.get_arns(resources), [resources[0]['PoolArn']])


class SmsVoiceConfigurationSetTest(BaseTest):

    def test_sms_voice_configuration_set_query(self):
        session_factory = self.replay_flight_data(
            'test_sms_voice_configuration_set_query')
        p = self.load_policy(
            {'name': 'sms-voice-configuration-set-query',
             'resource': 'aws.sms-voice-configuration-set',
             'filters': [
                 {'tag:c7n-test': 'query'},
                 {'DefaultMessageFeedbackEnabled': False}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            p.resource_manager.get_arns(resources), [resources[0]['ConfigurationSetArn']])


class SmsVoiceRegistrationTest(BaseTest):

    def test_sms_voice_registration_query(self):
        session_factory = self.replay_flight_data('test_sms_voice_registration_query')
        p = self.load_policy(
            {'name': 'sms-voice-registration-query',
             'resource': 'aws.sms-voice-registration',
             'filters': [{'tag:c7n-test': 'query'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            p.resource_manager.get_arns(resources), [resources[0]['RegistrationArn']])
