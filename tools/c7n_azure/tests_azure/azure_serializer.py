# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json


class AzureSerializer:

    def deserialize(self, cassette_string):
        return json.loads(cassette_string)

    def serialize(self, cassette_dict):
        error_message = (
            "Does this HTTP interaction contain binary data? "
            "If so, use a different serializer (like the yaml serializer) "
            "for this request?"
        )

        try:
            return json.dumps(cassette_dict, indent=4)
        except UnicodeDecodeError as original:  # py2
            raise UnicodeDecodeError(
                original.encoding,
                b"Error serializing cassette to JSON",
                original.start,
                original.end,
                original.args[-1] + error_message
            )
        except TypeError:  # py3
            raise TypeError(error_message)
