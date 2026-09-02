# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .ps_connector_utils import PS_TITLES


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ``res.partner.title`` no longer exists in Odoo 19, and the Product
    # Selector service only accepts a fixed enum anyway, so the module ships
    # its own selection instead of trying to map an Odoo title record.
    ps_title = fields.Selection(
        PS_TITLES,
        string='PS Title',
        default='Mr',
        help='Title sent to the Product Selector service for this contact '
             '(customer.persons[].title).',
    )
    ps_fax = fields.Char(
        string='Fax',
        size=20,
        help='Fax number sent to the Product Selector service.',
    )
    ps_ext = fields.Char(
        string='Extension',
        size=10,
        help='Phone extension sent to the Product Selector service '
             '(customer.persons[].ext).',
    )

    @api.model
    def _ps_default_title_for(self, partner):
        """Fallback used when a contact has no explicit ``ps_title``."""
        return partner.ps_title or 'Mr'
