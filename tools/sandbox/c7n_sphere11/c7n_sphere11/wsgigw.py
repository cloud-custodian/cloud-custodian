# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import urllib
import sys

from cStringIO import StringIO


def invoke(app, event):
    environ = create_wsgi_request(event)
    return create_gw_response(app, environ)


def create_gw_response(app, wsgi_env):
    """Create an api gw response from a wsgi app and environ.
    """
    response = {}
    buf = []
    result = []

    def start_response(status, headers, exc_info=None):
        result[:] = [status, headers]
        return buf.append

    appr = app(wsgi_env, start_response)
    close_func = getattr(appr, 'close', None)
    try:
        buf.extend(list(appr))
    finally:
        close_func and close_func()

    response['body'] = ''.join(buf)
    response['statusCode'] = result[0].split(' ', 1)[0]
    response['headers'] = {}

    for k, v in result[1]:
        response['headers'][k] = v
    if 'Content-Length' not in response['headers']:
        response['headers']['Content-Length'] = str(len(response['body']))
    if 'Content-Type' not in response['headers']:
        response['headers']['Content-Type'] = 'text/plain'
    return response


def create_wsgi_request(event, server_name='apigw'):
    """Create a wsgi environment from an apigw request.
    """
    path = urllib.url2pathname(event['path'])
    script_name = (
        event['headers']['Host'].endswith('.amazonaws.com') and
        event['requestContext']['stage'] or '').encode('utf8')
    query = event['queryStringParameters']
    query_string = query and urllib.urlencode(query) or ""
    body = event['body'] and event['body'].encode('utf8') or ''

    environ = {
        'HTTPS': 'on',
        'PATH_INFO': path.encode('utf8'),
        'QUERY_STRING': query_string.encode('utf8'),
        'REMOTE_ADDR': event[
            'requestContext']['identity']['sourceIp'].encode('utf8'),
        'REQUEST_METHOD': event['httpMethod'].encode('utf8'),
        'SCRIPT_NAME': script_name,
        'SERVER_NAME': server_name.encode('utf8'),
        'SERVER_PORT': '80'.encode('utf8'),
        'SERVER_PROTOCOL': u'HTTP/1.1'.encode('utf8'),

        'wsgi.errors': sys.stderr,
        'wsgi.input': StringIO(body),
        'wsgi.multiprocess': False,
        'wsgi.multithread': False,
        'wsgi.run_once': False,
        'wsgi.url_scheme': u'https'.encode('utf8'),
        'wsgi.version': (1, 0),
    }

    headers = event['headers']
    # Input processing
    if event['httpMethod'] in ("POST", "PUT", "PATCH"):
        if 'Content-Type' in headers:
            environ['CONTENT_TYPE'] = headers['Content-Type']
        environ['CONTENT_LENGTH'] = str(len(body))

    for header in list(event['headers'].keys()):
        wsgi_name = "HTTP_" + header.upper().replace('-', '_')
        environ[wsgi_name] = headers[header].encode('utf8')

    if script_name:
        path_info = environ['PATH_INFO']
        if script_name in path_info:
            environ['PATH_INFO'].replace(script_name, '')

    # Extract remote user from event
    remote_user = None
    if event['requestContext'].get('authorizer'):
        remote_user = event[
            'requestContext']['authorizer'].get('principalId')
    elif event['requestContext'].get('identity'):
        remote_user = event['requestContext']['identity'].get('userArn')
    if remote_user:
        environ['REMOTE_USER'] = remote_user

    # apigw aware integrations
    environ['apigw.request'] = event['requestContext']
    environ['apigw.stagevars'] = event['stageVariables']

    return environ
