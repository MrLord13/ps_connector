# -*- coding: utf-8 -*-
from odoo import fields, models

from .ps_connector_utils import PS_CURRENCIES, PS_ROLES


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ps_connector_protocol = fields.Selection(
        [('http', 'HTTP'), ('https', 'HTTPS')],
        string='Protocol',
        config_parameter='ps_connector.protocol',
        default='http',
    )
    ps_connector_host = fields.Char(
        string='Service Host',
        config_parameter='ps_connector.host',
        help='Domain or IP address of the Product Selector service, without protocol or port '
             '(e.g. product-selector.example.com or 46.209.99.90).',
    )
    ps_connector_port = fields.Integer(
        string='Service Port',
        config_parameter='ps_connector.port',
        default=65143,
        help='Leave empty to omit the port from the request URL.',
    )
    ps_connector_endpoint = fields.Char(
        string='API Endpoint',
        config_parameter='ps_connector.endpoint',
        default='/api/odoo/inquiries/store',
        help='Path called on the external service, e.g. /api/odoo/inquiries/store',
    )
    ps_connector_timeout = fields.Integer(
        string='Request Timeout (seconds)',
        config_parameter='ps_connector.timeout',
        default=30,
    )
    ps_connector_shared_secret = fields.Char(
        string='Shared Secret',
        config_parameter='ps_connector.shared_secret',
        help='Secret key used to sign the user token sent with every request. '
             'The external service must use the exact same value to validate the '
             'token, or call this Odoo instance back to validate it.',
    )
    ps_connector_token_expiry = fields.Integer(
        string='Token Validity (minutes)',
        config_parameter='ps_connector.token_expiry',
        default=15,
    )

    # ------------------------------------------------------------------
    # Payload options
    # ------------------------------------------------------------------
    ps_connector_payload_style = fields.Selection(
        [
            ('brackets', 'Bracket notation — customer[persons][0][name]'),
            ('json', 'JSON strings — customer = {...}'),
        ],
        string='Nested Object Encoding',
        config_parameter='ps_connector.payload_style',
        default='brackets',
        help='How the nested customer / inquiry / engineer objects are encoded inside the '
             'multipart/form-data body. Bracket notation is what PHP, Laravel and the "qs" '
             'parser expect; switch to JSON strings if the service reads the fields with '
             'json_decode().',
    )
    ps_connector_default_version = fields.Char(
        string='Default Inquiry Version',
        config_parameter='ps_connector.default_version',
        default='1.0',
    )
    ps_connector_default_currency = fields.Selection(
        PS_CURRENCIES,
        string='Default Inquiry Currency',
        config_parameter='ps_connector.default_currency',
        default='USD',
    )
    ps_connector_default_role = fields.Selection(
        PS_ROLES,
        string='Default User Role',
        config_parameter='ps_connector.default_role',
        default='Sales Engineer 1',
        help='Role assigned to users that have no Product Selector Role set on their '
             'user form. The value is sent verbatim to the remote service.',
    )
    ps_connector_user_block_key = fields.Char(
        string='User Block Name',
        config_parameter='ps_connector.user_block_key',
        default='user',
        help='Name of the multipart field carrying the logged in user identity '
             '(full name, email, role). Change it if the Product Selector service '
             'expects another name, e.g. "auth" or "odooUser".',
    )
    ps_connector_strict_validation = fields.Boolean(
        string='Block Incomplete Inquiries',
        config_parameter='ps_connector.strict_validation',
        default=True,
        help='When enabled, Odoo refuses to send an opportunity that is missing a field the '
             'Product Selector service marks as required, and lists what is missing. '
             'Disable it to send anyway and let the remote service answer.',
    )
    ps_connector_open_panel_url = fields.Boolean(
        string='Open Panel After Sending',
        config_parameter='ps_connector.open_panel_url',
        default=True,
        help='Open the URL returned by the service (data.url) in a new browser tab '
             'right after a successful call.',
    )
