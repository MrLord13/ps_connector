#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end self test of the Product Selector test service.

Builds exactly the request the Odoo module builds — it imports the module's
own ``build_multipart_parts`` encoder, so the bytes on the wire are the same
ones ``crm.lead.action_send_to_ps_connector`` produces — and posts it to the
running test service.

Run the service first::

    cd test_service && npm start

then, in another shell::

    python3 test_service/selftest.py                  # http://localhost:3000
    python3 test_service/selftest.py http://host:3000

It runs two cases:

1. a complete inquiry, which must be accepted (``ok: true`` + panel URL);
2. an inquiry with deliberate mistakes — including an unknown user role —
   which must be rejected with a list of problems, proving the validation
   really runs;
3. the English guard: the fields that must reach the service in English are
   recognised as Persian when they are, and the English override wins over
   the Odoo value.
"""

import base64
import json
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'models'))

from ps_connector_utils import (  # noqa: E402
    PS_LATIN_PATHS,
    build_multipart_parts,
    english_value,
    has_non_latin,
)

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:3000').rstrip('/')
ENDPOINT = os.environ.get('ENDPOINT', '/api/odoo/inquiries/store')
PAYLOAD_STYLE = os.environ.get('PAYLOAD_STYLE', 'brackets')

# A 1x1 transparent PNG, standing in for the customer logo / engineer avatar.
TINY_PNG = base64.b64decode(
    b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk'
    b'YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
)

# A token in the same shape the module produces (payload.signature). The test
# service only resolves it when ODOO_BASE_URL is set, so any well formed value
# works for a standalone run.
FAKE_TOKEN = (
    'eyJkYiI6Im9kb28xOSIsInVpZCI6MiwibG9naW4iOiJhZG1pbiJ9'
    '.c2VsZnRlc3Qtc2lnbmF0dXJlLW5vdC12ZXJpZmllZA'
)

AVATAR_NAME = 'alireza_nemati_2_avatar.png'


def valid_payload():
    return {
        'customer': {
            'company': 'Pars Jahd Service',
            'email': 'info@parsjahd.example.com',
            'phone': '+982112345678',
            'fax': '+982112345679',
            'address': 'No. 12, Valiasr Ave., 1966733561',
            'country': 'Iran',
            'state': 'Tehran',
            'city': 'Tehran',
            'persons': [
                {
                    'name': 'AliReza',
                    'family': 'Nemati',
                    'email': 'a.nemati@parsjahd.example.com',
                    'mobile': '+989121234567',
                    'fax': '+982112345679',
                    'ext': '210',
                    'position': 'Technical Manager',
                    'title': 'Mr',
                },
                {
                    'name': 'Sara',
                    'family': 'Ahmadi',
                    'email': 's.ahmadi@parsjahd.example.com',
                    'mobile': '+989121234568',
                    'fax': '',
                    'ext': '',
                    'position': 'Procurement',
                    'title': 'Ms',
                },
            ],
        },
        'inquiry': {
            'projectName': 'Compressor station upgrade',
            'projectDescription': 'Replacement of two centrifugal compressors.',
            'refNumber': 'ODOO-42',
            'version': '1.0',
            'fileNames': ['specification.pdf', AVATAR_NAME],
            'inquiryText': 'Customer asked for a full technical proposal.',
            'inquiryDate': '2026-09-02',
            'currency': 'EUR',
            'endUser': 'National Gas Company',
            'projectLocation': 'Tehran, Iran',
        },
        'engineer': {
            'fullName': 'AliReza Nemati',
            'avatarName': AVATAR_NAME,
            'phone': '+989121234567',
            'email': 'alireza@erpishro.com',
        },
        # Identity of the logged in Odoo user, used by the service to
        # authorise the caller.
        'user': {
            'fullName': 'AliReza Nemati',
            'email': 'alireza@erpishro.com',
            'role': 'Sales Manager',
        },
    }


def broken_payload():
    payload = valid_payload()
    payload['customer']['email'] = 'not-an-email'          # invalid format
    payload['customer']['fax'] = ''                        # required, empty
    payload['customer']['persons'][1]['title'] = 'Sir'     # outside the enum
    payload['inquiry']['currency'] = 'RIAL'                # outside the enum
    payload['inquiry']['version'] = 'v' * 25               # over 20 chars
    payload['inquiry']['inquiryDate'] = '02/09/2026'       # wrong date format
    payload['user']['role'] = 'Sales Engineer'             # outside the role enum
    payload['customer']['persons'][0]['email'] = ''        # required, empty
    return payload


def send(payload, files, logo):
    parts = build_multipart_parts(payload, FAKE_TOKEN, files, logo, PAYLOAD_STYLE)
    response = requests.post(
        f'{BASE_URL}{ENDPOINT}',
        files=parts,
        headers={'Authorization': f'Bearer {FAKE_TOKEN}', 'Accept': 'application/json'},
        timeout=30,
    )
    try:
        return response.status_code, response.json(), len(parts)
    except ValueError:
        return response.status_code, {'raw': response.text[:500]}, len(parts)


def show(title, status, body, part_count):
    print(f'\n--- {title} ---')
    print(f'parts sent : {part_count}')
    print(f'HTTP status: {status}')
    print(json.dumps(body, indent=2, ensure_ascii=False))


def main():
    files = [
        ('specification.pdf', b'%PDF-1.4 fake specification for the self test', 'application/pdf'),
        (AVATAR_NAME, TINY_PNG, 'image/png'),
    ]

    failures = []

    status, body, count = send(valid_payload(), files, TINY_PNG)
    show('CASE 1 — complete inquiry (expected: accepted)', status, body, count)
    if status == 200 and body.get('ok') and (body.get('data') or {}).get('uuid'):
        print('RESULT: PASS — the service accepted the inquiry and returned a panel URL.')
    else:
        failures.append('case 1 should have been accepted')
        print('RESULT: FAIL')

    status, body, count = send(broken_payload(), files, TINY_PNG)
    show('CASE 2 — inquiry with 8 deliberate mistakes (expected: rejected)', status, body, count)
    problems = ((body.get('error') or {}).get('problems')) or []
    if status == 422 and body.get('ok') is False and len(problems) >= 8:
        print(f'RESULT: PASS — the service caught {len(problems)} problem(s).')
    else:
        failures.append('case 2 should have been rejected with at least 8 problems')
        print('RESULT: FAIL')

    # --- CASE 3: the English guard, checked locally -----------------------
    print('\n--- CASE 3 — English guard (expected: Persian detected) ---')
    checks = [
        ('customer.company', 'پارس جهد', True),
        ('customer.company', 'Pars Jahd Service', False),
        ('person.name', 'علیرضا', True),
        ('person.name', 'AliReza', False),
        ('inquiry.projectName', 'ایستگاه تقویت فشار', True),
        ('engineer.fullName', 'Zurich AG', False),
    ]
    guard_ok = True
    for path, value, expected in checks:
        in_scope = path in PS_LATIN_PATHS
        detected = in_scope and has_non_latin(value)
        mark = 'OK ' if detected == expected else 'BAD'
        if detected != expected:
            guard_ok = False
        print(f'  {mark} {path:<28} {value!r:<28} persian={detected}')

    # Fields that never need a translation must stay out of the guard.
    for path in ('customer.email', 'customer.phone', 'customer.fax',
                 'person.mobile', 'person.ext', 'inquiry.refNumber',
                 'inquiry.version', 'inquiry.currency', 'inquiry.inquiryDate'):
        if path in PS_LATIN_PATHS:
            guard_ok = False
            print(f'  BAD {path} should not require English')

    # The English override must win over the Odoo value.
    if english_value('Pars Jahd Service', 'پارس جهد') != 'Pars Jahd Service':
        guard_ok = False
        print('  BAD the English override did not win over the Odoo value')
    if english_value('   ', 'Pars Jahd Service') != 'Pars Jahd Service':
        guard_ok = False
        print('  BAD a blank override should fall back to the Odoo value')

    if guard_ok:
        print('RESULT: PASS — Persian text is detected only where English is required.')
    else:
        failures.append('case 3: the English guard misclassified a field')
        print('RESULT: FAIL')

    print('\n' + '=' * 60)
    if failures:
        print('SELF TEST FAILED:')
        for failure in failures:
            print(' -', failure)
        return 1
    print('SELF TEST PASSED — the module encoder and the test service agree.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
