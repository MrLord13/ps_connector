# ps_connector
Product Selector Connector With Odoo (Pars Jahd Service)

## What's in this repo

- `ps_connector/` — Odoo 19 (Enterprise) addon. Adds a **Send to Product
  Selector** button on the CRM Opportunity form. Clicking it sends, over
  HTTP, to the external Product Selector service:
  - A signed token identifying the currently logged in Odoo user
    (`Authorization: Bearer <token>` header), so the external service knows
    which user triggered the action and can resume the flow without a new
    login. It can either verify the token itself (shared secret) or call
    Odoo's `/ps_connector/api/validate_token` endpoint to resolve it.
  - The opportunity's customer data: name, type (company/individual),
    phone, address.

  The external service's protocol/host/port/path, request timeout, signing
  secret and token lifetime are all configured from **Settings > CRM >
  Product Selector Connector** — nothing is hard-coded in the module.

- `test_service/` — a minimal Node.js/Express server that mimics the
  Product Selector service, used to verify that Odoo sends the data
  correctly. See `test_service/README.md` for how to run it and wire it up.

## Install the addon

1. Copy (or symlink) the `ps_connector/` folder into your Odoo `addons`
   path.
2. Restart Odoo, then go to **Apps**, remove the "Apps" filter, search for
   "Product Selector Connector" and install it (it depends on `crm`).
3. Configure the external service under **Settings > CRM > Product
   Selector Connector**.

## Quick end-to-end test

1. Start the test service (`test_service/`, see its README).
2. Point the module's settings to it (`http`, `localhost`, `3000`,
   `/api/opportunity`, any shared secret).
3. Open a CRM opportunity, fill in the customer name/phone/address, and
   click **Send to Product Selector**.
4. Check the test service's console output (and `GET /api/opportunity/log`)
   to confirm the payload and token arrived as expected.
