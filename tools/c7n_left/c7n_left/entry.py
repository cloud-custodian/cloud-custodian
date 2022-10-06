def initialize_iac():
    # import to get side effect registration into clouds
    from .providers.terraform import TerraformProvider  # noqa
