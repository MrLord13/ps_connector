from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ps_connector_protocol = fields.Selection(
        [('http', 'HTTP'), ('https', 'HTTPS')],
        string='Protocol',
        config_parameter='ps_connector.protocol',
        default='https',
    )
    ps_connector_host = fields.Char(
        string='Service Host',
        config_parameter='ps_connector.host',
        help='Domain or IP address of the Product Selector service, without protocol or port '
             '(e.g. product-selector.example.com or 192.168.1.50).',
    )
    ps_connector_port = fields.Integer(
        string='Service Port',
        config_parameter='ps_connector.port',
        default=443,
        help='Leave empty to omit the port from the request URL.',
    )
    ps_connector_endpoint = fields.Char(
        string='API Endpoint',
        config_parameter='ps_connector.endpoint',
        default='/api/opportunity',
        help='Path called on the external service, e.g. /api/opportunity',
    )
    ps_connector_timeout = fields.Integer(
        string='Request Timeout (seconds)',
        config_parameter='ps_connector.timeout',
        default=10,
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
