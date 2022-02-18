from .provider import AwsCloudControl  # noqa
from .meta import ResourceFinder


def initialize_awscc():
    """Load aws cloud control provider"""
    ResourceFinder.attach()
