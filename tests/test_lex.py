from .common import BaseTest


class LexV2Bot(BaseTest):

    def test_lexv2_cross_account(self):
        factory = self.replay_flight_data("test_lexv2_cross_account")
        p = self.load_policy(
            {
                "name": "lexv2-bot-cross-account",
                "resource": "lexv2-bot",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['CrossAccountViolations'][0]['Resource'],
          'arn:aws:lex:us-east-1:644160558196:bot/OTM2WO3PEY')


class Lexv2BotAlias(BaseTest):
    def test_tag_action(self):
        session_factory = self.replay_flight_data('test_lex_botalias_tag_action')
        p = self.load_policy(
            {
                "name": "tag-lexv2-bot-alias",
                "resource": "lexv2-bot-alias",
                "actions": [
                    {"type": "tag", "key": "Department", "value": "International"},
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
