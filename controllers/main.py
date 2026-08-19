import json

from odoo import http
from odoo.http import request

from ..models.ps_connector_utils import verify_user_token


class PSConnectorController(http.Controller):
    """Public endpoint the external service can call back with the token it
    received from Odoo, so it can identify the logged in user without
    requiring a new authentication step."""

    @http.route('/ps_connector/api/validate_token', type='http', auth='public', methods=['POST'], csrf=False)
    def validate_token(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data or b'{}')
        except ValueError:
            data = {}
        token = data.get('token') or kwargs.get('token')

        if not token:
            result = {'valid': False, 'error': 'missing_token'}
        else:
            payload = verify_user_token(request.env, token)
            if not payload:
                result = {'valid': False, 'error': 'invalid_or_expired_token'}
            elif payload.get('db') != request.env.cr.dbname:
                result = {'valid': False, 'error': 'database_mismatch'}
            else:
                user = request.env['res.users'].sudo().browse(payload['uid']).exists()
                if not user:
                    result = {'valid': False, 'error': 'user_not_found'}
                else:
                    result = {
                        'valid': True,
                        'user': {
                            'id': user.id,
                            'login': user.login,
                            'name': user.name,
                            'email': user.email,
                        },
                        'expires_at': payload.get('exp'),
                    }

        return request.make_response(
            json.dumps(result),
            headers=[('Content-Type', 'application/json')],
        )
