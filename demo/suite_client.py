"""
A signed-in session with Trellis Tools, as a browser has one: for demo/load.py.
Python's standard library only, so it runs wherever Python 3 does.
"""

import json
import ssl
import uuid
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener


class SuiteError(Exception):
    pass


class Suite:
    def __init__(self, url: str, verify: bool = True):
        self.url = url.rstrip('/')
        context = ssl.create_default_context()
        if not verify:                       # a local install's own certificate
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()), HTTPSHandler(context=context))
        self.username = None

    def call(self, method: str, path: str, body=None, files=None, form=None, raw: bool = False):
        headers = {'Accept': 'application/json'}
        data = None
        if files is not None:
            boundary = uuid.uuid4().hex
            parts = []
            for name, value in (form or {}).items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
            for name, filename, content, mime in files:
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                             f'Content-Type: {mime}\r\n\r\n'.encode() + content + b'\r\n')
            data = b''.join(parts) + f'--{boundary}--\r\n'.encode()
            headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
        elif body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        request = Request(self.url + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=120) as response:
                content = response.read()
        except HTTPError as exc:
            detail = exc.read().decode(errors='replace')
            try:
                detail = json.loads(detail).get('error') or json.loads(detail).get('message') or detail
            except (ValueError, AttributeError):
                pass
            raise SuiteError(f'{method} {path} as {self.username}: {exc.code} {str(detail)[:300]}') from None
        if raw:
            return content
        return json.loads(content) if content else {}

    def get(self, path):
        return self.call('GET', path)

    def post(self, path, body=None, **kw):
        return self.call('POST', path, body if body is not None else {}, **kw)

    def put(self, path, body=None):
        return self.call('PUT', path, body if body is not None else {})

    def sign_in(self, username: str, password: str) -> 'Suite':
        self.username = username
        self.call('POST', '/account/api/login', {'username': username, 'password': password})
        return self
