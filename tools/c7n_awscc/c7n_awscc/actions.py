# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

import jsonpatch

from c7n.actions import Action
from c7n.utils import local_session, type_schema


class ControlAction(Action):
    def get_identity(self, r):
        id_fields = self.manager.schema["primaryIdentifier"]
        idv = {}
        for idf in id_fields:
            idn = idf.rsplit("/", 1)[-1]
            idv[idn] = r[idn]
        if len(idv) == 1:
            return idv[idn]
        return json.dumps(idv)


class Delete(ControlAction):
    schema = type_schema("delete")

    def process(self, resources):
        client = local_session(self.manager.session_factory).client("cloudcontrol")
        for r in resources:
            client.delete_resource(
                TypeName=self.manager.resource_type.cfn_type,
                Identifier=self.get_identity(r),
            )


class Update(ControlAction):
    # schema is setup at resource type initialization

    def process(self, resources):
        client = local_session(self.manager.session_factory).client("cloudcontrol")
        for r in resources:
            patch = self.get_patch(r)
            client.update_resource(
                TypeName=self.manager.resource_type.cfn_type,
                Identifier=self.get_identity(r),
                PatchDocument=patch.to_string(),
            )

    def get_patch(self, r):
        tgt = dict(r)
        for k, v in self.data.items():
            if k == "type":
                continue
            tgt[k] = v
        return jsonpatch.make_patch(r, tgt)
