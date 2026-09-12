{
    'name': 'Product Selector Connector',
    'summary': 'Send CRM opportunity data to the external Product Selector service with an SSO-style user token',
    'description': """
Product Selector Connector
===========================
Adds a "Send to Product Selector" button on the CRM opportunity form.

Clicking it posts a ``multipart/form-data`` request to the Product Selector
service (``/api/odoo/inquiries/store`` by default) containing the four blocks
of the published API specification:

* ``customer`` - company name, logo, email, phone, fax, address, country,
  state, city and the array of contact persons (name, family, mobile, fax,
  ext, position, title).
* ``inquiry``  - project name and description, reference number, version,
  file names, inquiry text, inquiry date, currency, end user and project
  location.
* ``engineer`` - full name, avatar file name, phone and email of the Odoo
  user in charge.
* ``user``     - full name, email and Product Selector role of the logged in
  Odoo user, which is what the remote service uses to authorise the caller.
* ``files``    - every attachment of the opportunity, plus the engineer
  avatar.
* ``token``    - a signed token identifying the Odoo user, so the external
  service can continue the flow without asking for a new login.

On success the service answers ``{ok, message, data: {url, uuid}}``; the
inquiry UUID and panel URL are stored on the opportunity and the panel can
be opened straight from the form.

The service URL (protocol, host, port, endpoint) and the signing secret are
configurable from Settings > Product Selector Connector, nothing is
hard-coded.

A Node.js test service is provided under test_service/ in the repository; it
parses the multipart body, validates every field against the specification
and answers with the documented response shape.
""",
    'version': '19.0.2.2.0',
    'category': 'ERPishro Modules',
    'author': 'AliReza Nemati',
    'depends': ['crm'],
    'data': [
        'security/ir.model.access.csv',
        'views/crm_lead_views.xml',
        'views/res_partner_views.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/ps_connector_preview_views.xml',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'OPL-1',
}
