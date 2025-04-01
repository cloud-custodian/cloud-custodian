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

# class TestLexConversationLogs(BaseTest):
#     def test_conversationlogs_filter(self):
#         session_factory = self.replay_flight_data("test_lex_conversationlogs_filter")
#         p = self.load_policy(
#             {
#             "name": "test-lex-conversationLogs",
#             "resource": "lexv2-bot",
#             "filters": [{"type": "conversationlogs",
#                     #  "key": "conversationLogSettings.textLogSettings[].enabled",
#                      "key": "conversationLogSettings.textLogSettings [?enabled == `false`]",
#                     #  "op": "contains",
#                      "value": "not-null",
#                  }
#              ],
#              },
#              session_factory=session_factory,
#         )
#         resources = p.run()
#         self.assertEqual(len(resources), 1)

#         resource = resource[0]
#         self.assertIn("conversationLogSettings", resource)
#         self.assertTrue(
#             any(
#                 log.get("enabled", "false")
#                 for log in resource["conversationLogSettings"].get("textLogSettings", [])
#             ),
#             "no textLogSettings with enabled=True found in resource"
#         )

class TestLexConversationLogs(BaseTest):
    def test_conversationlogs_filter(self):
        session_factory = self.record_flight_data("test_lex_conversationlogs_filter")
        p = self.load_policy(
            {
                "name": "test-lex-conversationLogs",
                "resource": "lexv2-bot",
                "filters": [
                    {
                        "type": "conversationlogs",
                        "key": "conversationLogSettings.textLogSettings[?enabled == `false`]",
                        "value": "not-null",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        print("Filtered BS resources:", resources)  # Debugging statement
        self.assertEqual(len(resources), 1)

        resource = resources[0]
        self.assertIn("conversationLogSettings", resource)
        self.assertTrue(
            any(
                log.get("enabled", True) is False
                for log in resource["conversationLogSettings"].get("textLogSettings", [])
            ),
            "no textLogSettings with enabled=False found in resource"
        )