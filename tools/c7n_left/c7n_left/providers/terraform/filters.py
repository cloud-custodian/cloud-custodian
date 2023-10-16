import json
from pathlib import Path

from c7n.filters import Filter

TAGGABLE_DATA_PATH = Path(__file__).parent / ".." / ".." / "data" / "taggable.json"


class Taggable(Filter):
    """Filter out resource types that are not taggable."""

    _taggable = None

    @classmethod
    def get_tag_data(cls):
        if cls._taggable:
            return cls._taggable
        with open(TAGGABLE_DATA_PATH) as fh:
            taggable = json.load(fh)
            for k, v in list(taggable.items()):
                taggable[k] = set(v)
            cls._taggable = taggable
        return cls._taggable

    @classmethod
    def is_taggable(cls, resources):
        if not resources:
            return False
        tag_data = cls.get_tag_data()
        r = resources[0]
        tf_path = r["__tfmeta"]["label"]
        provider = tf_path.split("_", 1)[0]
        if provider not in tag_data:
            return False
        tf_type = tf_path.split(".")[0]
        if tf_type not in tag_data[provider]:
            return False
        return True

    def process(self, resources, event=None):
        # policies and filters are invoked per resource type
        # so either all of a set is taggable or none.
        if self.is_taggable(resources):
            return resources
        return []
