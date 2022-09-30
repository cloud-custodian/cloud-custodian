from .exceptions import InvalidTeardownMode


class TeardownOption:
    DEFAULT = None
    ON = "on"
    OFF = "off"
    IGNORE = "ignore"

    _options = (
        "on",
        "off",
        "default",
        "ignore",
    )

    def __init__(self, default="on"):
        self.set_default(default)

    def set_default(self, default):
        if default == "default" or default not in self._options:
            default = "on"
        self._default = default

    def resolve(self, option=None):
        if option is self.DEFAULT:
            return self._default

        option = option.lower()

        if option not in self._options:
            raise InvalidTeardownMode(
                "{} is not a valid option: {}".format(option, ",".join(self._options))
            )

        return option


teardown = TeardownOption()
