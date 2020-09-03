import re
from .constants import ACCOUNT_ID


class TerraformHooks():
    def pytest_terraform_modify_state(self, tfstate):
        """ Sanitize functional testing account data """
        tfstate.update(re.sub(r'([0-9]+){12}', ACCOUNT_ID, str(tfstate)))
