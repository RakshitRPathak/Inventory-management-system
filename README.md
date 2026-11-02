# Inventory Management System

[![tests](https://github.com/RakshitRPathak/Inventory-management-system/actions/workflows/ci.yml/badge.svg)](https://github.com/RakshitRPathak/Inventory-management-system/actions/workflows/ci.yml)

A small inventory service for a warehouse of electrical parts. It tracks stock and suggests reorders from real
demand, reconciles the books against weight sensors in the storage bins, and keeps an audit log that shows if anyone
has edited history. An optional assistant answers questions about current stock from the live data.

Python 3.9+ and the standard library only: no dependencies to install. About 400 lines of code and 15 tests.

## Run it

```bash
python -m unittest discover -s tests -v    # 15 tests, under a second
python demo.py                              # seeds data, simulates a sensor, prints results, starts the API on :8080
```

The demo creates `inventory.db`, an `admin` user and a `sensor01` user with the passwords in `demo.py`. Change them
before you run it anywhere but your own machine. Set `OPENAI_API_KEY` to have the assistant answer with an OpenAI model;
without it, answers fall back to the closest matching records.

## What it does

**Stock that can't go negative.** Every stock change is one transaction that updates the quantity, writes a movement
row and appends to the audit log, or rolls all three back. A guard in code and a `CHECK (qty >= 0)` constraint in the
schema both refuse a change that would take stock below zero.

**Reorders from real demand.** For each product the service works out average daily demand over the last 30 days. It
suggests a reorder when stock falls below `demand × (supplier lead time + 3 safety days)` or the product's fixed
reorder point, whichever is higher, and sizes the order to cover the next 30 days. Suggestions are sorted by how many
days of stock are left.

**Sensors that check the books.** Each storage bin has a weight sensor. Two ideas come from industrial control systems:

- *Report by exception:* the sensor node only transmits when the weight moves by more than a deadband, so a noisy
  sensor doesn't flood the network.
- *Edge anomaly detection:* the node keeps a rolling window and flags any reading more than 3.5 standard deviations
  from it, which catches sudden drops from theft, spills or a failing sensor.

The gateway converts weight to units and compares it with the book quantity. A mismatch raises a `shrinkage` or
`unrecorded_receipt` alert; a reading from a bin with no product raises `unknown_bin`.

**An audit log that shows tampering.** Every action (user creation, failed logins, product changes, stock changes,
alerts) is appended to a hash chain: each row stores the SHA-256 of the previous row's hash plus its own contents.
Editing or deleting any row breaks the chain, and `GET /audit/verify` reports the first row that doesn't match.

**Access control.** Passwords are hashed with salted PBKDF2-SHA256 (200,000 iterations) and compared in constant
time. Tokens are HMAC-signed and expire after an hour. Every API route checks a permission against the caller's role:

| Role | Can |
|---|---|
| `admin` | everything |
| `manager` | read, adjust stock, verify the audit log |
| `clerk` | read and adjust stock |
| `sensor` | send telemetry only, so a compromised device can't read or change stock |

**Questions about stock.** `POST /ask` builds documents from the current products, reorder suggestions and recent
alerts, retrieves the closest ones with TF-IDF, and sends them to the model with a prompt that says to answer only from
that context, cite SKUs, never invent quantities, and ignore any instructions found inside the data. If there's no API
key or the call fails, it returns the matching records instead.

## API

All routes except `/login` need `Authorization: Bearer <token>`.

| Route | Permission | What it does |
|---|---|---|
| `POST /login` | none | `{"username", "password"}` → `{"token"}` |
| `GET /products` | read | All products |
| `GET /reorder` | read | Reorder suggestions |
| `POST /stock` | adjust | `{"sku", "delta", "reason"}` → new quantity; 409 if it would go negative |
| `POST /telemetry` | telemetry | `{"bin_id", "weight", "ts", "edge_anomaly"}` → `ok` or an alert |
| `POST /ask` | read | `{"question"}` → answer and the source records |
| `GET /audit/verify` | audit | `{"intact", "first_bad_row"}` |

Errors are JSON: 400 for malformed input, 401 for a missing or bad token, 403 for a missing permission, 409 for a
business-rule violation. Request bodies over 1 MB are rejected.

## Layout

| File | Job |
|---|---|
| `inventory/db.py` | Schema and connection |
| `inventory/service.py` | Users, products, stock movements, demand and reorder logic |
| `inventory/security.py` | Password hashing, roles, signed tokens, the audit hash chain |
| `inventory/telemetry.py` | Sensor node (deadband, anomaly detection) and the reconciliation gateway |
| `inventory/rag.py` | Retrieval and the grounded prompt for `/ask` |
| `inventory/server.py` | HTTP routing, auth and error handling |
| `tests/test_all.py` | 15 tests: stock rules, reorders, passwords, token tampering and expiry, roles, audit tampering, telemetry alerts, retrieval and fallback |

## Limits

- The audit chain catches edits made without recomputing the hashes. Someone with write access to the database could
  rebuild the whole chain, so a real deployment should key it with an HMAC secret kept outside the database, or
  publish the latest hash somewhere the database can't change.
- The token format is a minimal signed token, not a full JWT; the signing key is generated at startup, so tokens don't
  survive a restart. Use a JWT library and a configured key in production.
- SQLite and the built-in `http.server` keep it dependency-free, which suits a single process, not heavy concurrent load.
- The sensors are simulated in `demo.py`; nothing here has been connected to real hardware.
