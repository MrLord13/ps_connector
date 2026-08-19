'use strict';

const express = require('express');

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;
// Base URL of the Odoo instance, used to resolve the user token back into a
// user, e.g. http://localhost:8069. Optional: without it the service only
// reports whether a token was present.
const ODOO_BASE_URL = process.env.ODOO_BASE_URL;

const received = [];

app.post('/api/opportunity', async (req, res) => {
  const authHeader = req.headers['authorization'] || '';
  const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : null;

  console.log('\n=== Incoming request from Odoo ===');
  console.log('Time:', new Date().toISOString());
  console.log('Token present:', Boolean(token));
  console.log('Body:', JSON.stringify(req.body, null, 2));

  let odooUser = null;
  let tokenValidationError = null;

  if (token && ODOO_BASE_URL) {
    try {
      const response = await fetch(`${ODOO_BASE_URL}/ps_connector/api/validate_token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      const result = await response.json();
      console.log('Token validation result:', result);
      if (result.valid) {
        odooUser = result.user;
      } else {
        tokenValidationError = result.error || 'invalid_token';
      }
    } catch (err) {
      tokenValidationError = err.message;
      console.error('Failed to validate token against Odoo:', err.message);
    }
  }

  const entry = {
    received_at: new Date().toISOString(),
    token_present: Boolean(token),
    odoo_user: odooUser,
    token_validation_error: tokenValidationError,
    payload: req.body,
  };
  received.push(entry);

  res.status(200).json({
    received: true,
    token_present: entry.token_present,
    odoo_user: odooUser,
    token_validation_error: tokenValidationError,
    customer: req.body.customer || null,
  });
});

// Lets you inspect everything the test service has received so far,
// e.g. GET http://localhost:3000/api/opportunity/log
app.get('/api/opportunity/log', (req, res) => {
  res.json(received);
});

app.get('/health', (req, res) => res.json({ status: 'ok' }));

app.listen(PORT, () => {
  console.log(`Product Selector test service listening on port ${PORT}`);
  if (ODOO_BASE_URL) {
    console.log(`Will validate tokens against ${ODOO_BASE_URL}`);
  } else {
    console.log('ODOO_BASE_URL is not set: tokens will be reported as "present" but not resolved to a user.');
    console.log('Set it, e.g. ODOO_BASE_URL=http://localhost:8069, to test the full SSO-style flow.');
  }
});
