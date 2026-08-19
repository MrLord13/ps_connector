# ps_connector
Product Selector Connector With Odoo (Pars Jahd Service)

## What's in this repo

This repository *is* the Odoo 19 (Enterprise) addon — `__manifest__.py`
sits at the repo root, alongside `models/`, `views/`, `controllers/`. It
adds a **Send to Product Selector** button on the CRM Opportunity form.
Clicking it sends, over HTTP, to the external Product Selector service:
  - A signed token identifying the currently logged in Odoo user
    (`Authorization: Bearer <token>` header), so the external service knows
    which user triggered the action and can resume the flow without a new
    login. It can either verify the token itself (shared secret) or call
    Odoo's `/ps_connector/api/validate_token` endpoint to resolve it.
  - The opportunity's customer data: name, type (company/individual),
    phone, address.

The external service's protocol/host/port/path, request timeout, signing
secret and token lifetime are all configured from **Settings > Product
Selector Connector** — nothing is hard-coded in the module.

- `test_service/` — a minimal Node.js/Express server that mimics the
  Product Selector service, used to verify that Odoo sends the data
  correctly. See `test_service/README.md` for how to run it and wire it up.

## Install the addon

1. Copy (or clone) this repository into your Odoo `addons` path, as a
   folder named `ps_connector` (e.g. `custom/ps_connector/`), so that
   `custom/ps_connector/__manifest__.py` exists.
2. Restart Odoo, then go to **Apps**, remove the "Apps" filter, search for
   "Product Selector Connector" and install it (it depends on `crm`).
3. Configure the external service under **Settings > Product Selector
   Connector**.

## Quick end-to-end test

1. Start the test service (`test_service/`, see its README).
2. Point the module's settings to it (`http`, `localhost`, `3000`,
   `/api/opportunity`, any shared secret).
3. Open a CRM opportunity, fill in the customer name/phone/address, and
   click **Send to Product Selector**.
4. Check the test service's console output (and `GET /api/opportunity/log`)
   to confirm the payload and token arrived as expected.


## For Test Space
### Configure Ps Connector In Settings Page
1. Protocol > Http
2. Service Host > localhost
3. Service Port > 3000
4. API Endpoint > /api/opportunity
5. Request Timeout (seconds) > 10
6. Shared Secret > secret-123 (Optional SecretKey)
7. Token Validity (minutes) > 15

### Start NPM With Command 
$env:ODOO_BASE_URL="http://localhost:8069"; $env:PORT="3000"; npm start
OR
npm start

### Test opportunity In Odoo
1. Go To CRM Module
2. Open Random Record
3. Click Send To Product Selector On Statusbar 
4. You will see a success message if the connection was established correctly.

### See Logs In This Page 
http://localhost:3000/api/opportunity/log