import pytest

from c7n.config import Config
from c7n.exceptions import PolicyValidationError
from c7n.loader import PolicyLoader
from c7n.query import sources


class SourceTest:
    def __init__(self, manager):
        self.manager = manager
        self.config = manager.source_config


@pytest.fixture()
def testing_source():
    sources.register('testing', SourceTest)
    yield
    sources.unregister('testing')


class TestSchemaSource:
    @pytest.fixture(autouse=True)
    def setup(self, testing_source):
        self.loader = PolicyLoader(Config.empty())

    def load(self, policy_data):
        collection = self.loader.load_data({"policies": [policy_data]}, 'memory://')
        return collection.policies[0]

    def test_unknown_source(self):
        data = {
            "name": "test",
            "resource": "ec2",
            "source": "unknown",
        }
        with pytest.raises(PolicyValidationError) as err:
            self.load(data)
        assert "'unknown' is not valid under any of the given schemas" in str(err.value)

    def test_testing_source_name(self):
        data = {
            "name": "test",
            "resource": "ec2",
            "source": "testing",
        }
        p = self.load(data)
        source = p.resource_manager.source
        assert isinstance(source, SourceTest)
        assert source.manager.data == data
        assert source.config == {}

    def test_testing_source_object(self):
        data = {
            "name": "test",
            "resource": "ec2",
            "source": {
                "name": "testing",
                "query": "something",
            },
        }
        p = self.load(data)
        source = p.resource_manager.source
        assert isinstance(source, SourceTest)
        assert source.manager.data == data
        assert source.config == {
            "name": "testing",
            "query": "something",
        }
