# -*- coding: utf-8 -*-
import base64
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from .ps_connector_utils import (
    PS_CURRENCIES,
    build_multipart_parts,
    clip,
    generate_user_token,
    is_valid_email,
    split_person_name,
)

_logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = '/api/odoo/inquiries/store'


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # ------------------------------------------------------------------
    # Fields required by the Product Selector API that Odoo does not carry
    # ------------------------------------------------------------------
    ps_company_fax = fields.Char(
        string='Company Fax',
        size=20,
        compute='_compute_ps_company_fax', store=True, readonly=False,
        help='customer.fax — required by the Product Selector service.',
    )
    ps_ref_number = fields.Char(
        string='Inquiry Ref. Number',
        size=255,
        compute='_compute_ps_ref_number', store=True, readonly=False, copy=False,
        help='inquiry.refNumber — the customer reference of this inquiry.',
    )
    ps_version = fields.Char(
        string='Inquiry Version',
        size=20,
        default=lambda self: self._ps_default_version(),
        help='inquiry.version — base version of the inquiry.',
    )
    ps_inquiry_text = fields.Text(
        string='Inquiry Text',
        compute='_compute_ps_inquiry_text', store=True, readonly=False,
        help='inquiry.inquiryText — internal description about the inquiry.',
    )
    ps_inquiry_date = fields.Date(
        string='Inquiry Letter Date',
        default=fields.Date.context_today,
        help='inquiry.inquiryDate — date of the inquiry letter.',
    )
    ps_currency = fields.Selection(
        PS_CURRENCIES,
        string='Inquiry Currency',
        default=lambda self: self._ps_default_currency(),
        help='inquiry.currency — currency of the inquiry.',
    )
    ps_end_user = fields.Char(
        string='End User',
        size=256,
        compute='_compute_ps_end_user', store=True, readonly=False,
        help='inquiry.endUser',
    )
    ps_project_location = fields.Char(
        string='Project Location',
        size=256,
        compute='_compute_ps_project_location', store=True, readonly=False,
        help='inquiry.projectLocation',
    )
    ps_engineer_user_id = fields.Many2one(
        'res.users',
        string='Engineer',
        default=lambda self: self.env.user,
        help='Odoo user sent as the "engineer" block of the request.',
    )
    ps_attachment_ids = fields.Many2many(
        'ir.attachment',
        'ps_connector_lead_attachment_rel', 'lead_id', 'attachment_id',
        string='Files to Send',
        help='Files sent with the inquiry. Leave empty to send every '
             'attachment linked to this opportunity.',
    )

    # ------------------------------------------------------------------
    # Result of the last successful call
    # ------------------------------------------------------------------
    ps_inquiry_uuid = fields.Char(string='PS Inquiry UUID', readonly=True, copy=False)
    ps_panel_url = fields.Char(string='PS Panel URL', readonly=True, copy=False)
    ps_last_sent_on = fields.Datetime(string='Last Sent to PS', readonly=True, copy=False)

    # ------------------------------------------------------------------
    # Defaults / computes
    # ------------------------------------------------------------------
    @api.model
    def _ps_default_version(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'ps_connector.default_version', '1.0') or '1.0'

    @api.model
    def _ps_default_currency(self):
        icp = self.env['ir.config_parameter'].sudo()
        configured = icp.get_param('ps_connector.default_currency')
        allowed = [code for code, _label in PS_CURRENCIES]
        if configured in allowed:
            return configured
        company_currency = self.env.company.currency_id.name
        if company_currency in allowed:
            return company_currency
        return 'USD'

    @api.depends('partner_id')
    def _compute_ps_company_fax(self):
        for lead in self:
            if not lead.ps_company_fax:
                partner = lead.partner_id.commercial_partner_id or lead.partner_id
                lead.ps_company_fax = partner.ps_fax or False

    @api.depends('name')
    def _compute_ps_ref_number(self):
        for lead in self:
            if not lead.ps_ref_number:
                lead.ps_ref_number = 'ODOO-%s' % (lead.id or '')

    @api.depends('description')
    def _compute_ps_inquiry_text(self):
        for lead in self:
            if lead.ps_inquiry_text:
                continue
            text = html2plaintext(lead.description) if lead.description else ''
            lead.ps_inquiry_text = text.strip() or lead.name or ''

    @api.depends('partner_name', 'contact_name', 'partner_id')
    def _compute_ps_end_user(self):
        for lead in self:
            if not lead.ps_end_user:
                lead.ps_end_user = (
                    lead.partner_name or lead.partner_id.name or lead.contact_name or ''
                )

    @api.depends('city', 'country_id')
    def _compute_ps_project_location(self):
        for lead in self:
            if lead.ps_project_location:
                continue
            parts = [lead.city, lead.country_id.name]
            lead.ps_project_location = ', '.join(p for p in parts if p)

    # ------------------------------------------------------------------
    # Payload construction
    # ------------------------------------------------------------------
    def _ps_get_company_partner(self):
        """Partner holding the company level data of the customer."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return self.env['res.partner']
        return partner.commercial_partner_id or partner

    def _ps_get_contact_partners(self):
        """Partners used to build ``customer.persons``."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return self.env['res.partner']
        company = partner.commercial_partner_id or partner
        if company != partner:
            # The opportunity points at an individual contact already.
            return partner
        children = company.child_ids.filtered(lambda p: p.type == 'contact' and p.name)
        return children or (company if not company.is_company else self.env['res.partner'])

    def _ps_prepare_person(self, partner):
        first_name, family_name = split_person_name(partner.name)
        return {
            'name': clip(first_name, 'person.name'),
            'family': clip(family_name, 'person.family'),
            'mobile': clip(partner.phone, 'person.mobile'),
            'fax': clip(partner.ps_fax, 'person.fax'),
            'ext': clip(partner.ps_ext, 'person.ext'),
            'position': clip(partner.function, 'person.position'),
            'title': partner.ps_title or 'Mr',
        }

    def _ps_prepare_persons(self):
        """Build ``customer.persons``, falling back to the lead's own contact
        information when the customer has no contact records."""
        self.ensure_one()
        persons = [self._ps_prepare_person(p) for p in self._ps_get_contact_partners()]
        persons = [p for p in persons if p['name']]
        if persons:
            return persons

        fallback_name = self.contact_name or self.partner_name or self.name
        first_name, family_name = split_person_name(fallback_name)
        return [{
            'name': clip(first_name, 'person.name'),
            'family': clip(family_name, 'person.family'),
            'mobile': clip(self.phone, 'person.mobile'),
            'fax': clip(self.ps_company_fax, 'person.fax'),
            'ext': '',
            'position': clip(self.function, 'person.position'),
            'title': 'Mr',
        }]

    def _ps_prepare_customer(self):
        self.ensure_one()
        company_partner = self._ps_get_company_partner()

        address_parts = [
            self.street or company_partner.street,
            self.street2 or company_partner.street2,
            self.zip or company_partner.zip,
        ]
        address = ', '.join(part for part in address_parts if part)

        return {
            'company': clip(
                self.partner_name or company_partner.name or self.name,
                'customer.company',
            ),
            'email': clip(self.email_from or company_partner.email, 'customer.email'),
            'phone': clip(self.phone or company_partner.phone, 'customer.phone'),
            'fax': clip(self.ps_company_fax or company_partner.ps_fax, 'customer.fax'),
            'address': clip(address, 'customer.address'),
            # The specification spells this key "county" while describing it
            # as the country name; the key is sent exactly as specified.
            'county': clip(
                (self.country_id or company_partner.country_id).name,
                'customer.county',
            ),
            'state': clip(
                (self.state_id or company_partner.state_id).name,
                'customer.state',
            ),
            'city': clip(self.city or company_partner.city, 'customer.city'),
            'persons': self._ps_prepare_persons(),
        }

    def _ps_prepare_inquiry(self, file_names):
        self.ensure_one()
        return {
            'projectName': clip(self.name, 'inquiry.projectName'),
            'projectDescription': clip(
                html2plaintext(self.description) if self.description else '',
                'inquiry.projectDescription',
            ),
            'refNumber': clip(self.ps_ref_number, 'inquiry.refNumber'),
            'version': clip(self.ps_version, 'inquiry.version'),
            'fileNames': file_names,
            'inquiryText': clip(self.ps_inquiry_text, 'inquiry.inquiryText'),
            'inquiryDate': self.ps_inquiry_date.isoformat() if self.ps_inquiry_date else '',
            'currency': self.ps_currency or '',
            'endUser': clip(self.ps_end_user, 'inquiry.endUser'),
            'projectLocation': clip(self.ps_project_location, 'inquiry.projectLocation'),
        }

    def _ps_engineer_avatar_name(self, user):
        safe = ''.join(c if c.isalnum() else '_' for c in (user.name or 'engineer'))
        return f'{safe.strip("_").lower() or "engineer"}_{user.id}_avatar.png'

    def _ps_prepare_engineer(self, user):
        self.ensure_one()
        return {
            'fullName': clip(user.name, 'engineer.fullName'),
            'avatarName': self._ps_engineer_avatar_name(user),
            'phone': clip(user.partner_id.phone, 'engineer.phone'),
            'email': clip(user.email or user.login, 'engineer.email'),
        }

    def _ps_get_attachments(self):
        """Attachments sent in ``files``."""
        self.ensure_one()
        if self.ps_attachment_ids:
            return self.ps_attachment_ids
        return self.env['ir.attachment'].search([
            ('res_model', '=', 'crm.lead'),
            ('res_id', '=', self.id),
        ])

    def _ps_get_customer_logo(self):
        """Binary logo sent as ``customer.logo``.

        Falls back to the current Odoo company logo, because the remote
        service requires the field and most CRM customers have no image.
        """
        self.ensure_one()
        company_partner = self._ps_get_company_partner()
        return (
            company_partner.image_1920
            or self.partner_id.image_1920
            or self.env.company.logo
            or False
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _ps_validate_payload(self, payload):
        """Return the list of human readable problems found in ``payload``."""
        problems = []
        customer = payload['customer']
        inquiry = payload['inquiry']
        engineer = payload['engineer']

        required_customer = {
            'company': _('Customer > Company Name'),
            'phone': _('Customer > Phone'),
            'fax': _('Customer > Fax'),
            'address': _('Customer > Address (Street)'),
            'county': _('Customer > Country'),
            'state': _('Customer > State'),
            'city': _('Customer > City'),
        }
        for key, label in required_customer.items():
            if not customer.get(key):
                problems.append(label)

        if not customer.get('email'):
            problems.append(_('Customer > Email'))
        elif not is_valid_email(customer['email']):
            problems.append(_('Customer > Email (invalid format: %s)', customer['email']))

        if not customer.get('persons'):
            problems.append(_('Customer > Contact Persons (at least one)'))
        for index, person in enumerate(customer.get('persons') or [], start=1):
            for key, label in (
                ('name', _('First Name')),
                ('family', _('Last Name')),
                ('mobile', _('Phone')),
                ('position', _('Job Position')),
                ('title', _('Title')),
            ):
                if not person.get(key):
                    problems.append(_('Contact Person #%(index)s > %(label)s',
                                      index=index, label=label))

        required_inquiry = {
            'projectName': _('Inquiry > Project Name'),
            'refNumber': _('Inquiry > Ref. Number'),
            'version': _('Inquiry > Version'),
            'inquiryText': _('Inquiry > Inquiry Text'),
            'inquiryDate': _('Inquiry > Inquiry Date'),
            'currency': _('Inquiry > Currency'),
            'endUser': _('Inquiry > End User'),
            'projectLocation': _('Inquiry > Project Location'),
        }
        for key, label in required_inquiry.items():
            if not inquiry.get(key):
                problems.append(label)

        if not engineer.get('fullName'):
            problems.append(_('Engineer > Full Name'))
        if not engineer.get('phone'):
            problems.append(_('Engineer > Phone'))
        if not engineer.get('email'):
            problems.append(_('Engineer > Email'))
        elif not is_valid_email(engineer['email']):
            problems.append(_('Engineer > Email (invalid format: %s)', engineer['email']))

        return problems

    # ------------------------------------------------------------------
    # Request
    # ------------------------------------------------------------------
    def _ps_get_settings(self):
        icp = self.env['ir.config_parameter'].sudo()
        endpoint = icp.get_param('ps_connector.endpoint', DEFAULT_ENDPOINT) or DEFAULT_ENDPOINT
        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint
        return {
            'protocol': icp.get_param('ps_connector.protocol', 'https'),
            'host': icp.get_param('ps_connector.host'),
            'port': icp.get_param('ps_connector.port'),
            'endpoint': endpoint,
            'timeout': int(icp.get_param('ps_connector.timeout', 10) or 10),
            'payload_style': icp.get_param('ps_connector.payload_style', 'brackets') or 'brackets',
            'strict': icp.get_param('ps_connector.strict_validation', 'True') not in ('False', 'false', '0', ''),
            'open_panel': icp.get_param('ps_connector.open_panel_url', 'True') not in ('False', 'false', '0', ''),
        }

    def _ps_collect_files(self, attachments, engineer_avatar, avatar_name):
        """Return the ``(filename, content, mimetype)`` tuples sent as ``files[]``."""
        file_tuples = [
            (
                attachment.name,
                base64.b64decode(attachment.datas or b''),
                attachment.mimetype or 'application/octet-stream',
            )
            for attachment in attachments
        ]
        if engineer_avatar:
            file_tuples.append((avatar_name, engineer_avatar, 'image/png'))
        return file_tuples

    def action_send_to_ps_connector(self):
        self.ensure_one()
        settings = self._ps_get_settings()

        if not settings['host']:
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

        engineer_user = self.ps_engineer_user_id or self.env.user
        attachments = self._ps_get_attachments()
        file_names = [attachment.name for attachment in attachments]

        avatar_name = self._ps_engineer_avatar_name(engineer_user)
        engineer_avatar = engineer_user.partner_id.image_1920
        if engineer_avatar:
            engineer_avatar = base64.b64decode(engineer_avatar)
            file_names.append(avatar_name)

        payload = {
            'customer': self._ps_prepare_customer(),
            'inquiry': self._ps_prepare_inquiry(file_names),
            'engineer': self._ps_prepare_engineer(engineer_user),
        }

        problems = self._ps_validate_payload(payload)
        if problems:
            message = _(
                'The Product Selector service requires the following '
                'information before this opportunity can be sent:'
            )
            details = '\n'.join(' • %s' % problem for problem in problems)
            if settings['strict']:
                raise UserError('%s\n\n%s' % (message, details))
            _logger.warning('ps_connector: sending lead %s with missing data:\n%s',
                            self.id, details)

        logo = self._ps_get_customer_logo()
        if logo:
            logo = base64.b64decode(logo)

        file_tuples = self._ps_collect_files(attachments, engineer_avatar, avatar_name)
        parts = build_multipart_parts(
            payload, token, file_tuples, logo, settings['payload_style'],
        )

        try:
            port = int(settings['port'] or 0)
        except (TypeError, ValueError):
            port = 0
        port_part = f':{port}' if port > 0 else ''
        url = f"{settings['protocol']}://{settings['host']}{port_part}{settings['endpoint']}"

        headers = {
            # The token is also sent as a form field, as per the API
            # specification; the header is kept for services that prefer it.
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        }

        _logger.info('ps_connector: POST %s (%s parts, %s file(s))',
                     url, len(parts), len(file_tuples))

        try:
            response = requests.post(
                url, files=parts, headers=headers, timeout=settings['timeout'],
            )
        except requests.exceptions.RequestException as exc:
            _logger.exception('ps_connector: could not reach %s', url)
            raise UserError(_('Could not reach the Product Selector service: %s', exc))

        try:
            result = response.json()
        except ValueError:
            result = {}

        if not response.ok or not result.get('ok'):
            error = result.get('message') or result.get('error') or response.text[:500]
            code = result.get('code') or response.status_code
            raise UserError(_(
                'The Product Selector service rejected the request '
                '(code %(code)s):\n\n%(error)s',
                code=code, error=error,
            ))

        data = result.get('data') or {}
        self.write({
            'ps_inquiry_uuid': data.get('uuid') or self.ps_inquiry_uuid,
            'ps_panel_url': data.get('url') or self.ps_panel_url,
            'ps_last_sent_on': fields.Datetime.now(),
        })

        body = _('Inquiry sent to the Product Selector service.')
        if data.get('uuid'):
            body += _(' Inquiry UUID: %s', data['uuid'])
        self.message_post(body=body)

        if data.get('url') and settings['open_panel']:
            return {
                'type': 'ir.actions.act_url',
                'url': data['url'],
                'target': 'new',
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sent'),
                'message': result.get('message') or _(
                    'The inquiry was successfully sent to the Product Selector service.'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_open_ps_panel(self):
        self.ensure_one()
        if not self.ps_panel_url:
            raise UserError(_('This opportunity has not been sent to the Product Selector yet.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self.ps_panel_url,
            'target': 'new',
        }
