# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .ps_connector_utils import PS_ROLES


class ResUsers(models.Model):
    _inherit = 'res.users'

    ps_role = fields.Selection(
        PS_ROLES,
        string='Product Selector Role',
        default=lambda self: self._ps_default_role(),
        help='Role sent to the Product Selector service together with the full name '
             'and the email address, so the service can authorise the logged in user. '
             'The value is sent verbatim and must be one of the roles the service knows.',
    )

    @api.model
    def _ps_default_role(self):
        allowed = [code for code, _label in PS_ROLES]
        configured = self.env['ir.config_parameter'].sudo().get_param(
            'ps_connector.default_role', 'Sales Engineer 1')
        return configured if configured in allowed else 'Sales Engineer 1'

    def _ps_identity(self):
        """The ``user`` block sent to the Product Selector service."""
        self.ensure_one()
        return {
            'fullName': self.name or '',
            'email': self.email or self.login or '',
            'role': self.ps_role or self._ps_default_role(),
        }

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['ps_role']
