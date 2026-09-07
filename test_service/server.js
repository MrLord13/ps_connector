'use strict';

/**
 * Product Selector — test service
 *
 * Stands in for the real Product Selector API while developing the Odoo
 * `ps_connector` module. It accepts the multipart/form-data request described
 * in Fields.ods, validates every field against the specification (required,
 * max length, enum, email format, arrays), and answers with the documented
 * response shape:
 *
 *   success -> { ok: true,  message, data: { url, uuid } }
 *   failure -> { ok: false, message, code, error }
 *
 * No extra npm dependency: the multipart body is parsed here, and the bracket
 * notation (customer[persons][0][name]) is turned back into nested objects with
 * `qs`, which ships with express.
 */

const crypto = require('crypto');
const express = require('express');
const qs = require('qs');

const app = express();

const PORT = process.env.PORT || 3000;
const ENDPOINT = process.env.ENDPOINT || '/api/odoo/inquiries/store';
// Base URL of the Odoo instance, used to resolve the user token back into a
// user, e.g. http://localhost:8069. Optional: without it the service only
// reports whether a token was present.
const ODOO_BASE_URL = process.env.ODOO_BASE_URL;
// Base URL returned to Odoo as `data.url` (the panel the user is sent to).
const PANEL_BASE_URL = process.env.PANEL_BASE_URL || `http://localhost:${PORT}/panel`;
// Set STRICT=0 to log validation problems but still answer ok:true.
const STRICT = process.env.STRICT !== '0';

const received = [];

// ---------------------------------------------------------------------------
// Specification (Fields.ods)
// ---------------------------------------------------------------------------

const TITLES = ['Mr', 'Mrs', 'Miss', 'Ms'];
const CURRENCIES = ['USD', 'EUR', 'GBP', 'AED', 'IRR', 'CNY', 'MYR'];
// Roles the Product Selector service knows; sent verbatim by Odoo.
const ROLES = [
  'Sales Engineer 1',
  'Sales Manager',
  'Sales Secretary',
  'Commercial Manager',
  'Production Manager',
  'Warehouse Officer',
];
// Name of the block carrying the logged in Odoo user identity. Must match
// "User Block Name" in the Odoo settings.
const USER_BLOCK = process.env.USER_BLOCK || 'user';

// [required, maxLength|null, kind]
const CUSTOMER_SPEC = {
  company: [true, 256, 'string'],
  email: [true, 256, 'email'],
  phone: [true, 20, 'string'],
  fax: [true, 20, 'string'],
  address: [true, 256, 'string'],
  county: [true, 100, 'string'],
  state: [true, 100, 'string'],
  city: [true, 100, 'string'],
};

const PERSON_SPEC = {
  name: [true, 256, 'string'],
  family: [true, 256, 'string'],
  mobile: [true, 15, 'string'],
  fax: [false, 15, 'string'],
  ext: [false, 10, 'string'],
  position: [true, 100, 'string'],
  title: [true, null, 'enum:title'],
};

const INQUIRY_SPEC = {
  projectName: [true, 255, 'string'],
  projectDescription: [false, 10000, 'string'],
  refNumber: [true, 255, 'string'],
  version: [true, 20, 'string'],
  inquiryText: [true, 10000, 'string'],
  inquiryDate: [true, null, 'date'],
  currency: [true, null, 'enum:currency'],
  endUser: [true, 256, 'string'],
  projectLocation: [true, 256, 'string'],
};

const ENGINEER_SPEC = {
  fullName: [true, 256, 'string'],
  avatarName: [true, null, 'string'],
  phone: [true, 15, 'string'],
  email: [true, 256, 'email'],
};

// Identity of the logged in Odoo user, used by the service to authorise
// the caller (full name + email + role).
const USER_SPEC = {
  fullName: [true, 256, 'string'],
  email: [true, 256, 'email'],
  role: [true, null, 'enum:role'],
};

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}([T ].*)?$/;

// ---------------------------------------------------------------------------
// Minimal multipart/form-data parser
// ---------------------------------------------------------------------------

function headerParam(headerValue, param) {
  const extended = new RegExp(`${param}\\*=([^;]+)`, 'i').exec(headerValue);
  if (extended) {
    const value = extended[1].trim();
    const match = /^[^']*'[^']*'(.*)$/.exec(value);
    try {
      return decodeURIComponent(match ? match[1] : value);
    } catch (err) {
      return match ? match[1] : value;
    }
  }
  const quoted = new RegExp(`${param}="([^"]*)"`, 'i').exec(headerValue);
  if (quoted) return quoted[1];
  const bare = new RegExp(`${param}=([^;]+)`, 'i').exec(headerValue);
  return bare ? bare[1].trim() : null;
}

function parsePart(buffer) {
  const separator = buffer.indexOf('\r\n\r\n');
  if (separator === -1) return null;

  const headers = {};
  buffer
    .subarray(0, separator)
    .toString('utf8')
    .split('\r\n')
    .forEach((line) => {
      const index = line.indexOf(':');
      if (index > 0) {
        headers[line.slice(0, index).trim().toLowerCase()] = line.slice(index + 1).trim();
      }
    });

  const disposition = headers['content-disposition'] || '';
  return {
    name: headerParam(disposition, 'name'),
    filename: headerParam(disposition, 'filename'),
    contentType: headers['content-type'] || null,
    body: buffer.subarray(separator + 4),
  };
}

function parseMultipart(buffer, boundary) {
  const parts = [];
  const delimiter = Buffer.from(`--${boundary}`);

  let cursor = buffer.indexOf(delimiter);
  if (cursor === -1) return parts;
  cursor += delimiter.length;

  while (cursor < buffer.length) {
    if (buffer.subarray(cursor, cursor + 2).toString('latin1') === '--') break; // closing delimiter
    cursor += 2; // skip the CRLF after the delimiter

    const next = buffer.indexOf(delimiter, cursor);
    if (next === -1) break;

    const part = parsePart(buffer.subarray(cursor, next - 2)); // -2 strips the trailing CRLF
    if (part && part.name) parts.push(part);
    cursor = next + delimiter.length;
  }

  return parts;
}

/** Turn the flat parts into { fields (nested), files }. */
function buildBody(parts) {
  const pairs = [];
  const files = [];

  parts.forEach((part) => {
    if (part.filename !== null && part.filename !== undefined) {
      files.push({
        field: part.name,
        filename: part.filename,
        contentType: part.contentType,
        size: part.body.length,
        sha256: crypto.createHash('sha256').update(part.body).digest('hex').slice(0, 16),
      });
    } else {
      pairs.push([part.name, part.body.toString('utf8')]);
    }
  });

  const query = pairs
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&');
  const fields = qs.parse(query, { depth: 12, arrayLimit: 2000, parameterLimit: 5000 });

  // The Odoo module can also send the three blocks as JSON strings
  // (Settings > Nested Object Encoding = "JSON strings").
  ['customer', 'inquiry', 'engineer', USER_BLOCK].forEach((key) => {
    if (typeof fields[key] === 'string') {
      try {
        fields[key] = JSON.parse(fields[key]);
      } catch (err) {
        /* leave as-is, validation will report it */
      }
    }
  });

  return { fields, files };
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function checkBlock(spec, block, path, problems) {
  if (!block || typeof block !== 'object') {
    problems.push(`${path}: missing or not an object`);
    return;
  }
  Object.entries(spec).forEach(([field, [required, maxLength, kind]]) => {
    const raw = block[field];
    const value = raw === undefined || raw === null ? '' : String(raw).trim();

    if (!value) {
      if (required) problems.push(`${path}.${field}: required but empty`);
      return;
    }
    if (maxLength && value.length > maxLength) {
      problems.push(`${path}.${field}: ${value.length} chars, max ${maxLength}`);
    }
    if (kind === 'email' && !EMAIL_RE.test(value)) {
      problems.push(`${path}.${field}: "${value}" is not a valid email address`);
    }
    if (kind === 'date' && !DATE_RE.test(value)) {
      problems.push(`${path}.${field}: "${value}" is not a YYYY-MM-DD date`);
    }
    if (kind === 'enum:title' && !TITLES.includes(value)) {
      problems.push(`${path}.${field}: "${value}" not in [${TITLES.join(', ')}]`);
    }
    if (kind === 'enum:currency' && !CURRENCIES.includes(value)) {
      problems.push(`${path}.${field}: "${value}" not in [${CURRENCIES.join(', ')}]`);
    }
    if (kind === 'enum:role' && !ROLES.includes(value)) {
      problems.push(`${path}.${field}: "${value}" not in [${ROLES.join(' | ')}]`);
    }
  });
}

function validate(fields, files) {
  const problems = [];
  const { customer, inquiry, engineer } = fields;

  checkBlock(CUSTOMER_SPEC, customer, 'customer', problems);

  const persons = customer && customer.persons;
  if (!Array.isArray(persons) || persons.length === 0) {
    problems.push('customer.persons: required, at least one contact person');
  } else {
    persons.forEach((person, index) => {
      checkBlock(PERSON_SPEC, person, `customer.persons[${index}]`, problems);
    });
  }

  const logo = files.find((file) => file.field === 'customer[logo]' || file.field === 'logo');
  if (!logo) problems.push('customer.logo: required binary file part is missing');

  checkBlock(INQUIRY_SPEC, inquiry, 'inquiry', problems);

  const fileNames = (inquiry && inquiry.fileNames) || [];
  if (fileNames && !Array.isArray(fileNames)) {
    problems.push('inquiry.fileNames: expected an array');
  }

  checkBlock(ENGINEER_SPEC, engineer, 'engineer', problems);
  checkBlock(USER_SPEC, fields[USER_BLOCK], USER_BLOCK, problems);

  const uploaded = files.filter((file) => file.field !== 'customer[logo]');
  if (Array.isArray(fileNames)) {
    fileNames.forEach((name) => {
      if (!uploaded.some((file) => file.filename === name)) {
        problems.push(`inquiry.fileNames: "${name}" has no matching part in files[]`);
      }
    });
  }

  if (!fields.token) problems.push('token: required but empty');

  return problems;
}

// ---------------------------------------------------------------------------
// Token resolution against Odoo
// ---------------------------------------------------------------------------

async function resolveToken(token) {
  if (!token || !ODOO_BASE_URL) {
    return { user: null, error: token ? null : 'missing_token' };
  }
  try {
    const response = await fetch(`${ODOO_BASE_URL}/ps_connector/api/validate_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    const result = await response.json();
    return result.valid
      ? { user: result.user, error: null }
      : { user: null, error: result.error || 'invalid_token' };
  } catch (err) {
    return { user: null, error: err.message };
  }
}

// ---------------------------------------------------------------------------
// Console report
// ---------------------------------------------------------------------------

function report(fields, files, problems, odooUser) {
  const customer = fields.customer || {};
  const inquiry = fields.inquiry || {};
  const engineer = fields.engineer || {};
  const persons = Array.isArray(customer.persons) ? customer.persons : [];

  console.log('\n========== Incoming inquiry from Odoo ==========');
  console.log('Time      :', new Date().toISOString());
  console.log('Token     :', fields.token ? `${String(fields.token).slice(0, 24)}...` : '(none)');
  console.log('Odoo user :', odooUser ? `${odooUser.name} <${odooUser.login}>` : '(not resolved)');
  console.log('--- customer ---');
  console.log(JSON.stringify({ ...customer, persons: `${persons.length} person(s)` }, null, 2));
  persons.forEach((person, index) => {
    console.log(`  person[${index}]:`, JSON.stringify(person));
  });
  console.log('--- inquiry ---');
  console.log(JSON.stringify(inquiry, null, 2));
  console.log('--- engineer ---');
  console.log(JSON.stringify(engineer, null, 2));
  console.log(`--- ${USER_BLOCK} (logged in Odoo user) ---`);
  console.log(JSON.stringify(fields[USER_BLOCK] || {}, null, 2));
  console.log('--- files ---');
  if (!files.length) {
    console.log('  (none)');
  }
  files.forEach((file) => {
    console.log(`  ${file.field.padEnd(16)} ${file.filename} (${file.contentType}, ${file.size} bytes)`);
  });

  if (problems.length) {
    console.log(`--- FAILED: ${problems.length} problem(s) ---`);
    problems.forEach((problem) => console.log('  x', problem));
  } else {
    console.log('--- OK: payload matches the specification ---');
  }
  console.log('===============================================\n');
}

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

app.use(express.raw({ type: 'multipart/form-data', limit: '100mb' }));
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

async function handleStore(req, res) {
  const contentType = req.headers['content-type'] || '';
  const boundary = headerParam(contentType, 'boundary');

  if (!boundary || !Buffer.isBuffer(req.body)) {
    return res.status(415).json({
      ok: false,
      message: 'Expected a multipart/form-data request body.',
      code: 415,
      error: { received_content_type: contentType || null },
    });
  }

  const parts = parseMultipart(req.body, boundary);
  const { fields, files } = buildBody(parts);
  const problems = validate(fields, files);

  const { user: odooUser, error: tokenError } = await resolveToken(fields.token);
  report(fields, files, problems, odooUser);

  const entry = {
    received_at: new Date().toISOString(),
    content_type: contentType,
    part_count: parts.length,
    fields,
    files,
    problems,
    odoo_user: odooUser,
    token_validation_error: tokenError,
  };
  received.push(entry);

  if (problems.length && STRICT) {
    return res.status(422).json({
      ok: false,
      message: `The inquiry does not match the specification (${problems.length} problem(s)).`,
      code: 422,
      error: { problems },
    });
  }

  const uuid = crypto.randomUUID();
  entry.uuid = uuid;

  return res.status(200).json({
    ok: true,
    message: 'Inquiry received.',
    data: {
      url: `${PANEL_BASE_URL}/${uuid}`,
      uuid,
    },
  });
}

app.post(ENDPOINT, handleStore);
// Convenience aliases so an older module configuration still reaches the handler.
if (ENDPOINT !== '/api/odoo/inquiries/store') app.post('/api/odoo/inquiries/store', handleStore);
app.post('/api/opportunity', handleStore);

// Everything received so far.
app.get('/api/odoo/inquiries/log', (req, res) => res.json(received));
app.get('/api/opportunity/log', (req, res) => res.json(received));

// Landing page the module opens after a successful call (data.url).
app.get('/panel/:uuid', (req, res) => {
  const entry = received.find((item) => item.uuid === req.params.uuid);
  if (!entry) return res.status(404).send('Unknown inquiry.');
  const inquiry = entry.fields.inquiry || {};
  res.send(
    '<!doctype html><meta charset="utf-8"><title>Product Selector (mock panel)</title>' +
      '<body style="font-family:system-ui;margin:3rem;max-width:48rem">' +
      '<h1>Mock Product Selector panel</h1>' +
      `<p>Inquiry <code>${req.params.uuid}</code> was received from Odoo` +
      `${entry.odoo_user ? ` for <b>${entry.odoo_user.name}</b>` : ''}.</p>` +
      `<p><b>${inquiry.projectName || ''}</b> - ref ${inquiry.refNumber || ''}</p>` +
      `<pre style="background:#f4f4f5;padding:1rem;overflow:auto">${JSON.stringify(entry.fields, null, 2)}</pre>` +
      '</body>',
  );
});

app.get('/health', (req, res) => res.json({ status: 'ok', endpoint: ENDPOINT, strict: STRICT }));

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Product Selector test service listening on port ${PORT}`);
    console.log(`Endpoint: POST ${ENDPOINT}`);
    console.log(`Strict validation: ${STRICT ? 'on' : 'off'}`);
    console.log(`User block name: ${USER_BLOCK}`);
    if (ODOO_BASE_URL) {
      console.log(`Will validate tokens against ${ODOO_BASE_URL}`);
    } else {
      console.log('ODOO_BASE_URL is not set: tokens are accepted but not resolved to a user.');
      console.log('Set it, e.g. ODOO_BASE_URL=http://localhost:8069, to test the full SSO-style flow.');
    }
  });
}

module.exports = app;
