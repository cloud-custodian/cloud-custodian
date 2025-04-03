import copy
from unittest import TestCase
from unittest.mock import MagicMock, patch

from c7n_mailer.jira_delivery import JiraDelivery
from common import MAILER_CONFIG
from c7n_mailer.target import MessageTargetMixin

EBS_NO_TAG = {
    "VolumeId": "vol-01",
    "Tags": [],
}

EBS_PRJB = {
    "VolumeId": "vol-02",
    "Tags": [{"Key": "jira_project", "Value": "PRJB"}],
}

EBS_MY_PROJECT = {
    "VolumeId": "vol-03",
    "Tags": [{"Key": "jira_project", "Value": "MY_PROJECT"}],
}

EBS_MY_ANOTHER_PROJECT = {
    "VolumeId": "vol-04",
    "Tags": [{"Key": "jira_project", "Value": "MY_ANOTHER_PROJECT"}],
}

EBS_EMPTY = {
    "VolumeId": "vol-05",
    "Tags": [{"Key": "jira_project", "Value": ""}],
}

SQS_MESSAGE_JIRA = {
    "account": "core-services-dev",
    "account_id": "123456789012",
    "action": {
        "to": ["jira"],
        "type": "notify",
        "transport": {"queue": "xxx", "type": "sqs"},
        "subject": "my subject",
        "jira": {"project": "PRJA"},
        "result": {},
    },
    "policy": {
        "resource": "ebs",
        "name": "ebs-mark-unattached-deletion",
    },
    "resources": [EBS_NO_TAG, EBS_PRJB],
}


class TestJiraDelivery(TestCase):
    @patch("jira.client.JIRA.server_info")
    def setUp(self, mock):
        self.config = copy.deepcopy(MAILER_CONFIG)
        self.delivery = JiraDelivery(self.config, MagicMock(), MagicMock())

    def test_get_project_to_resources(self):
        grouped = self.delivery.get_project_to_resources(SQS_MESSAGE_JIRA)
        assert grouped == {None: [EBS_NO_TAG, EBS_PRJB]}

        msg = copy.deepcopy(SQS_MESSAGE_JIRA)
        msg["action"]["to"] = ["jira://tag/jira_project"]
        grouped = self.delivery.get_project_to_resources(msg)
        assert grouped == {None: [EBS_NO_TAG], "PRJB": [EBS_PRJB]}

        # group resources that with an empty tag value
        msg["resources"] = [EBS_NO_TAG, EBS_EMPTY]
        grouped = self.delivery.get_project_to_resources(msg)
        assert grouped == {None: [EBS_NO_TAG], "": [EBS_EMPTY]}

    @patch("c7n_mailer.utils.get_rendered_jinja", return_value="mock content")
    @patch("jira.client.JIRA.create_issues")
    def test_process_jira_fields(self, mock_create_issues, mock_jinja):
        fields = {
            "project": "PRJA",
            # NOTE "priority" field is added by jira_custom_fields.DEFAULT
            "priority": {"name": "Medium"},
            "issuetype": {"name": "Task"},
            "summary": "my subject",
            "description": "mock content",
        }
        msg = copy.deepcopy(SQS_MESSAGE_JIRA)

        # case 1: to jira, 1 ticket is expected
        issue = MagicMock()
        issue.key = "PRJA-1"
        mock_create_issues.return_value = [{"issue": issue, "status": "Success"}]
        result = self.delivery.process(msg)
        assert result == ["PRJA-1"]
        assert mock_jinja.call_args[0][4] == "jira_template"
        assert mock_create_issues.call_args.kwargs["field_list"] == [fields]

        # case 2: to jira://tag/jira_project, 2 ticket is expected
        msg["action"]["to"] = ["jira://tag/jira_project"]
        self.delivery.process(msg)
        fields_b = copy.deepcopy(fields)
        fields_b["project"] = "PRJB"
        assert mock_create_issues.call_args.kwargs["field_list"] == [fields, fields_b]

    @patch("c7n_mailer.utils.get_rendered_jinja", return_value="mock content")
    @patch("jira.client.JIRA.create_issues")
    def test_process_jira_custom_fields(self, mock_create_issues, mock_jinja):
        fields = {
            "project": "MY_PROJECT",
            # NOTE "priority" field is added by jira_custom_fields.DEFAULT
            "priority": {"name": "Medium"},
            "issuetype": {"name": "Task"},
            "summary": "my subject",
            "description": "mock content",
        }
        # NOTE CAUTION: below cases are reusing vars like msg, issue and fields, so order matters
        # case 3: custom fields configured in jira_custom_fields are expected
        msg = copy.deepcopy(SQS_MESSAGE_JIRA)
        msg["action"]["to"] = ["jira://tag/jira_project"]
        msg["resources"] = [EBS_MY_PROJECT, EBS_MY_ANOTHER_PROJECT]

        fields_b = copy.deepcopy(fields)
        fields["customfield_10059"] = "value_for_the_field"
        fields_b["project"] = "MY_ANOTHER_PROJECT"
        fields_b.pop("priority")
        self.delivery.process(msg)
        assert mock_create_issues.call_args.kwargs["field_list"] == [fields, fields_b]

        # case 4: issue fields overriding priority:
        # jira_custom_fields.DEFAULT < policy.action.jira < jira_custom_fields.specific_project
        msg["action"]["jira"]["priority"] = {"name": "Low"}
        self.delivery.process(msg)
        fields["priority"] = {"name": "Low"}
        assert mock_create_issues.call_args.kwargs["field_list"] == [fields, fields_b]

        # case 5: ignore resources that with an empty tag value
        msg["resources"] = [EBS_MY_PROJECT, EBS_EMPTY]
        self.delivery.process(msg)
        assert mock_create_issues.call_args.kwargs["field_list"] == [fields]

    @patch("c7n_mailer.jira_delivery.JiraDelivery.process")
    def test_handle_targets(self, mock_jira):
        msg = copy.deepcopy(SQS_MESSAGE_JIRA)
        mtm = MessageTargetMixin()
        mtm.logger = MagicMock()
        mtm.session = MagicMock()
        mtm.config = self.config

        # NOTE test handle_targets to ensure msg is routed as expected
        mtm.handle_targets(msg, None, False, False)
        assert mock_jira.call_count == 0  # No call because JiraError is raised

        with patch("jira.client.JIRA.server_info"):
            # case 1: to jira
            mtm.handle_targets(msg, None, False, False)
            assert mock_jira.call_count == 1
            assert mock_jira.call_args[0][0] == msg

            # case 2: to jira://tag/xxx
            msg["action"]["to"] = ["jira://tag/jira_project"]
            mtm.handle_targets(msg, None, False, False)
            assert mock_jira.call_count == 2
            assert mock_jira.call_args[0][0] == msg

            # case 3: jira not in "to" list
            call_count = mock_jira.call_count
            msg["action"]["to"] = ["someone@example.com"]
            mtm.handle_targets(msg, None, False, False)
            assert mock_jira.call_count == call_count
