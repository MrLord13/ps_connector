# ps_connector

Product Selector Connector With Odoo (Pars Jahd Service) — Odoo 19.

## What it does

Adds a **Send to Product Selector** button on the CRM Opportunity form. It
posts a `multipart/form-data` request to the Product Selector API
(`POST /api/odoo/inquiries/store`) containing the five blocks of the
published specification (`Fields.ods`):

| Part | Content |
|---|---|
| `customer` | company, logo (file), email, phone, fax, address, county, state, city, `persons[]` |
| `persons[]` | name, family, mobile, fax, ext, position, title (`Mr`/`Mrs`/`Miss`/`Ms`) |
| `inquiry` | projectName, projectDescription, refNumber, version, `fileNames[]`, inquiryText, inquiryDate, currency, endUser, projectLocation |
| `engineer` | fullName, avatarName, phone, email |
| `files[]` | every attachment of the opportunity + the engineer avatar |
| `token` | signed token identifying the Odoo user (also sent as `Authorization: Bearer`) |

The service answers `{ ok, message, data: { url, uuid } }`. The module stores
`uuid` and `url` on the opportunity and opens the panel in a new browser tab.

Everything (protocol, host, port, endpoint, timeout, signing secret, token
lifetime, encoding style) is configured from **Settings > Product Selector
Connector** — nothing is hard-coded.

## Where the data comes from

| API field | Odoo source |
|---|---|
| `customer.company` | `crm.lead.partner_name`, else the customer's company partner name |
| `customer.logo` | customer company `image_1920`, falling back to the Odoo company logo |
| `customer.email` / `phone` | `email_from` / `phone` (falling back to the partner) |
| `customer.fax` | **Product Selector** tab > Company Fax (`ps_company_fax`) |
| `customer.address` | street + street2 + zip |
| `customer.county` / `state` / `city` | `country_id.name` / `state_id.name` / `city` |
| `customer.persons[]` | contacts of the customer company (`child_ids`), else the lead's own contact |
| `persons[].position` | partner `function` (Job Position) |
| `persons[].title` / `fax` / `ext` | **Product Selector** tab on the contact form (`ps_title`, `ps_fax`, `ps_ext`) |
| `inquiry.projectName` / `projectDescription` | `name` / `description` (HTML converted to plain text) |
| `inquiry.refNumber` / `version` / `inquiryText` / `inquiryDate` / `currency` / `endUser` / `projectLocation` | **Product Selector** tab on the opportunity |
| `inquiry.fileNames[]` | names of the sent files |
| `engineer.*` | the user selected in **Engineer** (defaults to the current user) |
| `files[]` | `ps_attachment_ids`, or every attachment of the opportunity |

Values longer than the documented maximum are truncated rather than rejected.
When a required field is empty the module refuses to send and lists exactly
what is missing (this can be turned off with *Block Incomplete Inquiries*).

### Notes on Odoo 19

- `mobile` no longer exists on `crm.lead` nor on `res.partner` in Odoo 19, so
  `persons[].mobile` is filled from `phone`.
- `res.partner.title` no longer exists either, and the API only accepts
  `Mr`/`Mrs`/`Miss`/`Ms`, so the module ships its own `ps_title` selection.

## Install

1. Copy this repository into your Odoo `addons` path as `ps_connector`, so
   that `custom/ps_connector/__manifest__.py` exists.
2. Restart Odoo, go to **Apps**, remove the "Apps" filter, search for
   "Product Selector Connector" and install it (depends on `crm`).
   If it is already installed, use **Upgrade**.
3. Configure it under **Settings > Product Selector Connector**.

## Settings

| Setting | Meaning |
|---|---|
| Protocol / Host / Port / Endpoint | Where the request goes (`http` / `46.209.99.90` / `65143` / `/api/odoo/inquiries/store`) |
| Request Timeout | Seconds before giving up |
| Shared Secret / Token Validity | Signing key and lifetime of the user token |
| Nested Object Encoding | `brackets` (PHP/Laravel style, default) or `json` strings |
| Default Inquiry Version / Currency | Defaults used on new opportunities |
| Block Incomplete Inquiries | Refuse to send when a required field is empty |
| Open Panel After Sending | Open `data.url` in a new tab on success |

## Test

- `test_service/` — a Node.js mock of the Product Selector API that validates
  the whole specification and answers with the documented response shape.
- `test_service/selftest.py` — reproduces the exact request the module sends
  (it imports the module's own encoder) and checks that a complete inquiry is
  accepted and a broken one is rejected. No Odoo instance required.

See `test_service/README.md`.

### Quick local test space

1. Settings > Product Selector Connector: `http`, `localhost`, `3000`,
   `/api/odoo/inquiries/store`, timeout `30`, secret `secret-123`,
   token validity `15`.
2. Start the service:
   `$env:ODOO_BASE_URL="http://localhost:8069"; $env:PORT="3000"; npm start`
3. Open an opportunity, fill the **Product Selector** tab, click
   **Send to Product Selector**.

---

ERPishro.com — AliReza Nemati
