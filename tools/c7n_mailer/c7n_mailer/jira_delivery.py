from typing import Dict, List

from c7n_mailer import utils
from jira import JIRA


class JiraDelivery:
    def __init__(self, config, session, logger):
        self.config = config
        self.session = session
        self.logger = logger
        self.url = config.get("jira_url")
        # The dict to set custom fields for each Jira project when needed
        self.custom_fields = config.get("jira_custom_fields", {})
        self.init_jira()

    def init_jira(self):
        token = utils.kms_decrypt(self.config, self.logger, self.session, "jira_token")
        self.logger.info(f'Decrypted jira_token: {token != self.config["jira_token"]}')
        self.config["jira_token"] = token
        # Use basic_auth attr to include both user name and API token
        basic_auth = tuple([self.config.get("jira_username"), token])
        self.client = JIRA(server=self.url, basic_auth=basic_auth)

    @staticmethod
    def get_resource_tag_value(resource, k):
        # return None if tag not found
        for t in resource.get("Tags", []):
            if t["Key"] == k:
                return t["Value"]

    def get_project_to_resources(self, message) -> Dict[str, List]:
        to_list = message.get("action", ()).get("to")
        tags = [to[11:] for to in to_list if to.startswith("jira://tag/")]
        # TODO maybe we should support multiple tags and distinations
        if len(tags) > 1:
            raise Exception(f"Only one jira distination is supported, got {tags}")

        grouped = {}
        for r in message["resources"]:
            project = self.get_resource_tag_value(r, tags[-1]) if len(tags) else None
            grouped.setdefault(project, []).append(r)
        # eg: { 'MYPROJECT': [resource1, resource2, etc], "":[...], None: [...] }
        return grouped

    def process(self, message) -> List:
        issue_list = []
        jira_fields = message["action"].get("jira", {})
        pr = self.get_project_to_resources(message)
        for project, resources in pr.items():
            # NOTE allow attaching an empty tag to resources to be ignored
            if project == "":
                self.logger.info(f"Ignore {len(resources)} resources as project value is empty")
                continue
            # NOTE use default value if no tag attached to these resources
            project = project or jira_fields.get("project")
            self.logger.info(
                "Sending account:%s policy:%s %s:%d jira:%s to %s"
                % (
                    message.get("account", ""),
                    message["policy"]["name"],
                    message["policy"]["resource"],
                    len(resources),
                    message["action"].get("jira_template", "default"),
                    project,
                )
            )
            issue = {}
            # Ref https://jira.readthedocs.io/examples.html#issues
            # Set the dict via action conf from policy PoV, via mailer conf from Jira projects PoV
            issue.update(**self.custom_fields.get("DEFAULT", {}))  # lowest priority
            issue.update(**jira_fields)
            issue.update(**self.custom_fields.get(project, {}))  # higher priority
            # NOTE remove `cannot-be-set` attributes in case some Jira projects can't have them
            [issue.pop(k) for k, v in list(issue.items()) if v == "cannot-be-set"]

            issue["project"] = project
            issue.setdefault("issuetype", {"name": "Task"})
            issue.setdefault("summary", utils.get_message_subject(message))
            issue.setdefault(
                "description",
                utils.get_rendered_jinja(
                    project,
                    message,
                    resources,
                    self.logger,
                    "jira_template",
                    "default",
                    self.config["templates_folders"],
                ),
            )
            self.logger.debug(issue)
            issue_list.append(issue)

        issueIds = self.create_issues(issue_list)
        message["action"]["result"].update(jira_issues=issueIds, jira_url=self.url)
        return issueIds

    def create_issues(self, issue_list) -> List:
        if not issue_list:
            return
        res = self.client.create_issues(field_list=issue_list)
        success_list = [i["issue"].key for i in res if i.get("status") == "Success"]
        self.logger.info(f"Created issues {success_list}")
        error_list = [i["error"] for i in res if i.get("error")]
        if error_list:
            self.logger.error(f"Failed to create issues {error_list}")
        return success_list
