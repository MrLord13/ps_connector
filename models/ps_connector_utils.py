import base64
import hashlib
import hmac
import json
import time


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


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
