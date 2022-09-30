class PytestTerraformError(Exception):
    """Pytest Terraform Exception Base Class"""


class TerraformCommandFailed(PytestTerraformError):
    """Terraform Command failed during execution"""


class InvalidOption(PytestTerraformError):
    """Invalid Option Error"""


class InvalidTeardownMode(InvalidOption):
    """Invalid Teardown Option Error"""


class InvalidState(PytestTerraformError):
    """Failure to load / parse state"""


class ModuleNotFound(ValueError):
    """module not found"""
