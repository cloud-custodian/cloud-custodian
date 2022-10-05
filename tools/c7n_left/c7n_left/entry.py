def initialize_iac():
    # import to get side effect registration into clouds
    from .provider import TerraformProvider  # noqa
