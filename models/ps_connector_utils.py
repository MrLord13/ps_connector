# -*- coding: utf-8 -*-
"""Helpers shared by the Product Selector Connector.

Contains the signed-token helpers (SSO-style identification of the Odoo
user) and the small sanitising helpers used while building the payload
described in the Product Selector API specification (Fields.ods).
"""

import base64
import hashlib
import hmac
import json
import re
import time

# ---------------------------------------------------------------------------
# Specification constants (Fields.ods)
# ---------------------------------------------------------------------------

#: Allowed values of ``customer.persons[].title``
PS_TITLES = [
    ('Mr', 'Mr'),
    ('Mrs', 'Mrs'),
    ('Miss', 'Miss'),
    ('Ms', 'Ms'),
]

#: Allowed values of ``inquiry.currency``
PS_CURRENCIES = [
    ('USD', 'USD'),
    ('EUR', 'EUR'),
    ('GBP', 'GBP'),
    ('AED', 'AED'),
    ('IRR', 'IRR'),
    ('CNY', 'CNY'),
    ('MYR', 'MYR'),
]

#: Roles recognised by the Product Selector service. The label is sent
#: verbatim, so the technical value and the label are kept identical.
PS_ROLES = [
    ('Sales Engineer 1', 'Sales Engineer 1'),
    ('Sales Manager', 'Sales Manager'),
    ('Sales Secretary', 'Sales Secretary'),
    ('Commercial Manager', 'Commercial Manager'),
    ('Production Manager', 'Production Manager'),
    ('Warehouse Officer', 'Warehouse Officer'),
]

#: Maximum length accepted by the remote service, per field path.
PS_MAX_LENGTHS = {
    'customer.company': 256,
    'customer.email': 256,
    'customer.phone': 20,
    'customer.fax': 20,
    'customer.address': 256,
    'customer.county': 100,
    'customer.state': 100,
    'customer.city': 100,
    'person.name': 256,
    'person.family': 256,
    'person.mobile': 15,
    'person.fax': 15,
    'person.ext': 10,
    'person.position': 100,
    'inquiry.projectName': 255,
    'inquiry.projectDescription': 10000,
    'inquiry.refNumber': 255,
    'inquiry.version': 20,
    'inquiry.inquiryText': 10000,
    'inquiry.endUser': 256,
    'inquiry.projectLocation': 256,
    'engineer.fullName': 256,
    'engineer.phone': 15,
    'engineer.email': 256,
    'user.fullName': 256,
    'user.email': 256,
}

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def user_role(user):
    """Role of ``user`` as the Product Selector service expects it."""
    role = getattr(user, 'ps_role', False)
    if role:
        return role
    default_role = env_default_role(user.env)
    return default_role


def env_default_role(env):
    return env['ir.config_parameter'].sudo().get_param(
        'ps_connector.default_role', 'Sales Engineer 1') or 'Sales Engineer 1'


def generate_user_token(env, user, expiry_minutes=None, secret=None):
    """Build a compact, signed token identifying ``user``.

    The token is a self-contained ``<payload>.<signature>`` pair (HMAC-SHA256),
    so the external service can verify it on its own if it also holds the
    shared secret, or call back the module's /ps_connector/api/validate_token
    endpoint to resolve it without requiring the user to log in again.
    """
    icp = env['ir.config_parameter'].sudo()
    secret = secret or icp.get_param('ps_connector.shared_secret')
    if not secret:
        raise ValueError('ps_connector.shared_secret is not configured')
    if expiry_minutes is None:
        expiry_minutes = int(icp.get_param('ps_connector.token_expiry', 15) or 15)

    now = int(time.time())
    payload = {
        'db': env.cr.dbname,
        'uid': user.id,
        'login': user.login,
        'name': user.name,
        'fullName': user.name,
        'email': user.email or user.login,
        'role': user_role(user),
        'iat': now,
        'exp': now + expiry_minutes * 60,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(',', ':')).encode())
    signature = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    return f'{payload_b64}.{signature_b64}'


def verify_user_token(env, token, secret=None):
    """Verify a token produced by :func:`generate_user_token`.

    Returns the decoded payload dict when the signature is valid and the
    token has not expired, otherwise ``None``.
    """
    icp = env['ir.config_parameter'].sudo()
    secret = secret or icp.get_param('ps_connector.shared_secret')
    if not secret or not token or '.' not in token:
        return None

    payload_b64, _, signature_b64 = token.partition('.')
    expected_signature = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    try:
        given_signature = _b64url_decode(signature_b64)
    except Exception:
        return None
    if not hmac.compare_digest(expected_signature, given_signature):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return None

    if payload.get('exp', 0) < time.time():
        return None

    return payload


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def clip(value, path):
    """Return ``value`` as a stripped string, truncated to the length the
    remote service accepts for ``path`` (see :data:`PS_MAX_LENGTHS`)."""
    if value is None or value is False:
        return ''
    text = str(value).strip()
    max_length = PS_MAX_LENGTHS.get(path)
    if max_length and len(text) > max_length:
        text = text[:max_length]
    return text


def is_valid_email(value):
    return bool(value) and bool(EMAIL_RE.match(str(value).strip()))


def split_person_name(full_name):
    """Split a display name into ``(name, family)``.

    The first token is the first name, everything after it is the family
    name. When only one token is available it is used for both, because the
    remote service requires the two of them.
    """
    parts = (full_name or '').strip().split()
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], ' '.join(parts[1:])


def flatten_for_multipart(value, prefix=''):
    """Flatten a nested dict/list into PHP/Laravel style bracket pairs.

    ``{'customer': {'persons': [{'name': 'Ali'}]}}`` becomes
    ``[('customer[persons][0][name]', 'Ali')]``, which is what a
    ``multipart/form-data`` endpoint written in PHP/Laravel (or parsed with
    ``qs``) expects for nested objects.

    ``None``/``False`` values are emitted as empty strings, booleans as
    ``'1'``/``'0'``. Binary payloads must not be passed here, they are added
    to the request as real file parts.
    """
    pairs = []
    if isinstance(value, dict):
        for key, sub_value in value.items():
            sub_prefix = f'{prefix}[{key}]' if prefix else str(key)
            pairs.extend(flatten_for_multipart(sub_value, sub_prefix))
    elif isinstance(value, (list, tuple)):
        for index, sub_value in enumerate(value):
            pairs.extend(flatten_for_multipart(sub_value, f'{prefix}[{index}]'))
    elif isinstance(value, bool):
        pairs.append((prefix, '1' if value else '0'))
    elif value is None or value is False:
        pairs.append((prefix, ''))
    else:
        pairs.append((prefix, str(value)))
    return pairs


def build_multipart_parts(payload, token, files, logo=None, payload_style='brackets'):
    """Build the ``files=`` argument of :func:`requests.post`.

    :param payload: dict of blocks to send (``customer``, ``inquiry``,
                    ``engineer``, ``user``, ...); every key becomes a
                    top-level field of the multipart body
    :param token:   signed user token, sent as the ``token`` form field
    :param files:   list of ``(filename, content_bytes, mimetype)`` tuples,
                    sent as repeated ``files[]`` parts
    :param logo:    raw bytes of the customer logo, sent as ``customer[logo]``
    :param payload_style: ``'brackets'`` (PHP/Laravel style, the default) or
                    ``'json'`` (each block sent as a JSON encoded string)

    Every value is passed through ``files`` (with ``None`` as the filename for
    scalars) so that ``requests`` always produces a ``multipart/form-data``
    body, even when no real file is attached.
    """
    parts = [('token', (None, token))]

    for key, block in payload.items():
        if payload_style == 'json':
            parts.append((
                key,
                (None, json.dumps(block, ensure_ascii=False), 'application/json'),
            ))
        else:
            for name, value in flatten_for_multipart(block, key):
                parts.append((name, (None, value)))

    if logo:
        parts.append(('customer[logo]', ('logo.png', logo, 'image/png')))

    for filename, content, mimetype in files:
        parts.append((
            'files[]',
            (filename, content, mimetype or 'application/octet-stream'),
        ))

    return parts
