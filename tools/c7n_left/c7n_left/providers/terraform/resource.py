# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#


class TerraformResource(dict):
    __slots__ = ("name", "data", "location")

    # pygments lexer
    format = "terraform"

    def __init__(self, name, data):
        self.name = name
        if isinstance(data["__tfmeta"], list):
            self.location = data["__tfmeta"][0]
        else:
            self.location = data["__tfmeta"]
        super().__init__(data)

    @property
    def id(self):
        return self.location["path"]

    @property
    def filename(self):
        return self.location["filename"]

    @property
    def line_start(self):
        return self.location["line_start"]

    @property
    def line_end(self):
        return self.location["line_end"]

    @property
    def src_dir(self):
        return self.location["src_dir"]

    def get_references(self):
        return self.location.get("refs", ())

    def get_source_lines(self):
        lines = (self.src_dir / self.filename).read_text().split("\n")
        return lines[self.line_start - 1 : self.line_end]  # noqa
