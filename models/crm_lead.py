import logging

import requests

from odoo import _, models
from odoo.exceptions import UserError

from .ps_connector_utils import generate_user_token

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def action_send_to_ps_connector(self):
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        protocol = icp.get_param('ps_connector.protocol', 'https')
        host = icp.get_param('ps_connector.host')
        port = icp.get_param('ps_connector.port')
        endpoint = icp.get_param('ps_connector.endpoint', '/api/opportunity') or '/api/opportunity'
        timeout = int(icp.get_param('ps_connector.timeout', 10) or 10)

        if not host:
            raise UserError(_(
                'The Product Selector service is not configured yet. '
                'Go to Settings > Product Selector Connector and set the service host.'
            ))

        try:
            token = generate_user_token(self.env, self.env.user)
        except ValueError:
            raise UserError(_(
                'The Product Selector service is not configured yet. '
                'Go to Settings > Product Selector Connector and set the shared secret.'
            ))

        port_part = f':{int(port)}' if port else ''
        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint
        url = f'{protocol}://{host}{port_part}{endpoint}'

        is_company = bool(self.partner_name) and not self.contact_name
        customer_type = 'company' if is_company else 'individual'
        customer_name = self.partner_name or self.contact_name or self.name

        address_parts = [
            self.street,
            self.street2,
            self.city,
            self.state_id.name if self.state_id else False,
            self.zip,
            self.country_id.name if self.country_id else False,
        ]
        formatted_address = ', '.join(part for part in address_parts if part)

        payload = {
            'event': 'crm_lead.send_to_ps_connector',
            'odoo': {
                'database': self.env.cr.dbname,
            },
            'opportunity': {
                'id': self.id,
                'name': self.name,
            },
            'customer': {
                'name': customer_name,
                'type': customer_type,
                'phone': self.phone or self.mobile or False,
                'address': {
                    'street': self.street,
                    'street2': self.street2,
                    'city': self.city,
                    'state': self.state_id.name if self.state_id else False,
                    'zip': self.zip,
                    'country': self.country_id.name if self.country_id else False,
                    'formatted': formatted_address,
                },
            },
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            _logger.exception('Failed to send opportunity %s to the Product Selector service', self.id)
            raise UserError(_('Could not reach the Product Selector service: %s') % exc)

        self.message_post(body=_('Opportunity data was sent to the Product Selector service.'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sent'),
                'message': _('Opportunity data was successfully sent to the Product Selector service.'),
                'type': 'success',
                'sticky': False,
            },
        }
