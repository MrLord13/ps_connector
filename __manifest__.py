{
    'name': 'Product Selector Connector',
    'summary': 'Send CRM opportunity data to the external Product Selector service with an SSO-style user token',
    'description': """
Product Selector Connector
===========================
Adds a "Send to Product Selector" button on the CRM opportunity form.

Clicking it sends, as an HTTP request to an external service:

* A signed token identifying the currently logged in Odoo user, so the
  external service can tell which user triggered the action and continue
  the flow without asking for a new login.
* The opportunity's customer data: name, type (company/individual),
  phone and address.

The external service URL (protocol, host, port, endpoint) and the
signing secret are configurable from Settings > Product Selector
Connector, nothing is hard-coded.

A minimal Node.js test service is provided under test_service/ in the
repository to verify that the data is sent and received correctly.
""",
    'version': '19.0.1.0.0',
    'category': 'ERPishro Modules',
    'author': 'AliReza Nemati',
    'license': 'LGPL-3',
    'depends': ['crm'],
    'data': [
        'views/crm_lead_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'installable': True,
    'application': False,
}
