# -*- coding: utf-8 -*-
from odoo import fields, models


class PsConnectorPreview(models.TransientModel):
    _name = 'ps.connector.preview'
    _description = 'Product Selector — Payload Preview'

    lead_id = fields.Many2one('crm.lead', string='Opportunity', required=True)
    target_url = fields.Char(string='Request URL', readonly=True)
    encoding = fields.Char(string='Encoding', readonly=True)
    problem_count = fields.Integer(string='Missing Fields', readonly=True)
    report = fields.Text(string='Payload', readonly=True)

    def action_send(self):
        """Send the inquiry straight from the preview."""
        self.ensure_one()
        return self.lead_id.action_send_to_ps_connector()
