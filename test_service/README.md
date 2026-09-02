# Product Selector — test service

A dependency-light Node.js/Express server that stands in for the real Product
Selector API while developing the `ps_connector` Odoo module.

It implements the contract described in `Fields.ods`:

| | |
|---|---|
| URL | `POST /api/odoo/inquiries/store` |
| Content-Type | `multipart/form-data` |
| Body | `customer`, `inquiry`, `engineer`, `files`, `token` |
| Response | `{ ok, message, data: { url, uuid } }` / `{ ok: false, message, code, error }` |

The service parses the multipart body itself (no `multer` / `busboy` needed),
rebuilds the nested `customer[persons][0][name]` keys with `qs`, then checks
**every** field against the specification: required, maximum length, enum
values (`title`, `currency`), email format, date format, and whether each
name listed in `inquiry.fileNames` really has a matching part in `files[]`.

## Run it

```bash
cd test_service
npm install
# ODOO_BASE_URL is optional; set it to let the test service resolve the
# user token back into a real Odoo user (the "no new login" flow).
ODOO_BASE_URL=http://localhost:8069 PORT=3000 npm start
```

Windows PowerShell:

```powershell
$env:ODOO_BASE_URL="http://localhost:8069"; $env:PORT="3000"; npm start
```

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `3000` | Listening port |
| `ENDPOINT` | `/api/odoo/inquiries/store` | Path handled (the real path is always handled too) |
| `ODOO_BASE_URL` | – | Odoo instance used to resolve the token into a user |
| `PANEL_BASE_URL` | `http://localhost:$PORT/panel` | Prefix of the `data.url` returned to Odoo |
| `STRICT` | `1` | Set to `0` to log validation problems but still answer `ok: true` |

## Routes

| Route | Purpose |
|---|---|
| `POST /api/odoo/inquiries/store` | Receives the inquiry (also aliased as `/api/opportunity`) |
| `GET /api/odoo/inquiries/log` | Everything received so far, as JSON |
| `GET /panel/:uuid` | Mock panel page — this is what `data.url` points at |
| `GET /health` | Health check |

## Configure Odoo

**Settings > Product Selector Connector**:

| Field | Value |
|---|---|
| Protocol | `http` |
| Service Host | `localhost` |
| Service Port | `3000` |
| API Endpoint | `/api/odoo/inquiries/store` |
| Request Timeout | `30` |
| Shared Secret | any value, e.g. `secret-123` |
| Token Validity | `15` |
| Nested Object Encoding | `Bracket notation` |
| Block Incomplete Inquiries | ✔ |
| Open Panel After Sending | ✔ |

If Odoo and the test service run on different hosts, replace `localhost` with
an address the Odoo server can reach.

## Self test (no Odoo required)

`selftest.py` imports the **module's own** multipart encoder
(`models/ps_connector_utils.build_multipart_parts`), so the bytes it puts on
the wire are exactly the ones `action_send_to_ps_connector` produces. Start
the service, then:

```bash
python3 selftest.py                       # against http://localhost:3000
python3 selftest.py http://localhost:3000
PAYLOAD_STYLE=json python3 selftest.py    # test the JSON-string encoding
```

It runs two cases:

1. a complete inquiry — must be **accepted** with a `uuid` and a panel URL;
2. an inquiry with six deliberate mistakes (bad email, empty required fax,
   title outside the enum, currency outside the enum, over-long version,
   wrong date format) — must be **rejected** with those six problems listed.

Expected output:

```
RESULT: PASS — the service accepted the inquiry and returned a panel URL.
RESULT: PASS — the service caught 6 problem(s).
SELF TEST PASSED — the module encoder and the test service agree.
```

## Full test with Odoo

1. Start the test service with `ODOO_BASE_URL` pointing at Odoo.
2. Open a CRM opportunity, fill the **Product Selector** tab, click
   **Send to Product Selector**.
3. The service console prints the three decoded blocks, the contact persons,
   the received files and a pass/fail verdict; on success Odoo opens the mock
   panel page in a new tab and stores the UUID on the opportunity.

## What the service receives

```
token                            = <signed odoo user token>
customer[company]                = Pars Jahd Service
customer[email]                  = info@parsjahd.example.com
customer[phone]                  = +982112345678
customer[fax]                    = +982112345679
customer[address]                = No. 12, Valiasr Ave., 1966733561
customer[county]                 = Iran
customer[state]                  = Tehran
customer[city]                   = Tehran
customer[persons][0][name]       = AliReza
customer[persons][0][family]     = Nemati
customer[persons][0][mobile]     = +989121234567
customer[persons][0][fax]        = +982112345679
customer[persons][0][ext]        = 210
customer[persons][0][position]   = Technical Manager
customer[persons][0][title]      = Mr
customer[logo]                   = <file: logo.png>
inquiry[projectName]             = Compressor station upgrade
inquiry[projectDescription]      = Replacement of two centrifugal compressors.
inquiry[refNumber]               = ODOO-42
inquiry[version]                 = 1.0
inquiry[fileNames][0]            = specification.pdf
inquiry[fileNames][1]            = alireza_nemati_2_avatar.png
inquiry[inquiryText]             = Customer asked for a full technical proposal.
inquiry[inquiryDate]             = 2026-09-02
inquiry[currency]                = EUR
inquiry[endUser]                 = National Gas Company
inquiry[projectLocation]         = Tehran, Iran
engineer[fullName]               = AliReza Nemati
engineer[avatarName]             = alireza_nemati_2_avatar.png
engineer[phone]                  = +989121234567
engineer[email]                  = alireza@erpishro.com
files[]                          = <file: specification.pdf>
files[]                          = <file: alireza_nemati_2_avatar.png>
```
