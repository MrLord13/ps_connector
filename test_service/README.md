# Product Selector test service

A minimal Node.js/Express server that stands in for the real Product
Selector service, used to check that the `ps_connector` Odoo module sends
opportunity data correctly.

## Run it

```bash
cd test_service
npm install
# ODOO_BASE_URL is optional; set it to let the test service resolve the
# user token back into a real Odoo user (the "no new login" flow).
ODOO_BASE_URL=http://localhost:8069 PORT=3000 npm start
```

## Configure Odoo

In Odoo, go to **Settings > Product Selector Connector** (under the main Settings menu) and set:

| Field           | Value                     |
|-----------------|---------------------------|
| Protocol        | `http`                    |
| Service Host    | `localhost`                |
| Service Port    | `3000`                     |
| API Endpoint    | `/api/opportunity`         |
| Shared Secret   | any value, e.g. `dev-secret` |

If Odoo and the test service run in different containers/hosts, replace
`localhost` with an address the Odoo server can reach (e.g. `host.docker.internal`
or the container name on a shared Docker network).

## Test the flow

1. Open a CRM opportunity in Odoo and click **Send to Product Selector** in
   the header.
2. Watch the test service's console output: it prints the received
   headers/body, and, if `ODOO_BASE_URL` is set, the result of validating
   the token against Odoo (the identified user).
3. Inspect everything received so far at `GET /api/opportunity/log`, or
   check the health check at `GET /health`.

## Example of what the service receives

```json
{
  "event": "crm_lead.send_to_ps_connector",
  "odoo": { "database": "odoo19" },
  "opportunity": { "id": 42, "name": "New office chairs" },
  "customer": {
    "name": "Acme Corp",
    "type": "company",
    "phone": "+98 21 1234 5678",
    "address": {
      "street": "123 Main St",
      "street2": false,
      "city": "Tehran",
      "state": "Tehran",
      "zip": "12345",
      "country": "Iran",
      "formatted": "123 Main St, Tehran, Tehran, 12345, Iran"
    }
  }
}
```

with an `Authorization: Bearer <token>` header carrying the signed user
token.
