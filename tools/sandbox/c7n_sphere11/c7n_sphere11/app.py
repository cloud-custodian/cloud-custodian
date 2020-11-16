# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from bottle import Bottle, request, response, abort

import json
import logging
import os

from audit import init_audit
from controller import Controller
from utils import Encoder

log = logging.getLogger("sphere11.api")
logging.basicConfig(level=logging.INFO)
config = json.load(open(os.environ.get('SPHERE11_CONFIG', 'config.json')))
controller = Controller(config)
audit = init_audit(config.get('log-group', 'sphere11'))

app = Bottle()


@app.route("/")
def index():
    return {"name": "sphere11", "version": "1.0"}


@app.route("/<account_id>/locks", method="GET")
@audit
def account_status(account_id):
    result = controller.db.iter_resources(account_id)
    response.content_type = "application/json"
    return json.dumps(result, indent=2, cls=Encoder)


@app.route("/<account_id>/locks/<resource_id>/lock", method="POST")
@audit
def lock(account_id, resource_id):
    request_data = request.json
    for rp in ('region',):
        if not request_data or rp not in request_data:
            abort(400, "Missing required parameter %s" % rp)
    return controller.lock(account_id, resource_id, request_data['region'])


@app.route("/<account_id>/locks/<resource_id>", method="GET")
def info(account_id, resource_id):
    request_data = request.query
    if resource_id.startswith('sg-') and 'parent_id' not in request_data:
        abort(400, "Missing required parameter parent_id")
    result = controller.info(
        account_id, resource_id, request_data.get('parent_id', resource_id))
    response.content_type = "application/json"
    return json.dumps(result, indent=2, cls=Encoder)


# this set to post to restrict permissions, perhaps another url space.
@app.route("/<account_id>/locks/delta", method="POST")
@audit
def delta(account_id):
    request_data = request.json
    for rp in ('region',):
        if not request_data or rp not in request_data:
            abort(400, "Missing required parameter %s" % rp)
    result = controller.get_account_delta(
        account_id, request_data['region'], api_url())
    response.content_type = "application/json"
    return json.dumps(result, indent=2, cls=Encoder)


@app.route("/<account_id>/locks/<resource_id>/unlock", method="POST")
@audit
def unlock(account_id, resource_id):
    return controller.unlock(account_id, resource_id)


def on_timer(event):
    return controller.process_pending()


def on_config_message(records):
    for r in records:
        json.loads(r['Sns'].get('Message'))


def on_db_change(records):
    pass


def api_url():
    parsed = request.urlparts
    url = "%s://%s%s" % (parsed.scheme, parsed.netloc, request.script_name)
    return url


@app.error(500)
def error(e):
    response.content_type = "application/json"
    return json.dumps({
        "status": e.status,
        "url": repr(request.url),
        "exception": repr(e.exception),
        #  "traceback": e.traceback and e.traceback.split('\n') or '',
        "body": repr(e.body)
    }, indent=2)
