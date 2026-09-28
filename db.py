"""SQL layer (resume: SQL / ERP exposure). SQLite so it runs anywhere."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
  pw_hash BLOB NOT NULL, salt BLOB NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppliers(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, lead_days INTEGER NOT NULL DEFAULT 7);
CREATE TABLE IF NOT EXISTS products(
  sku TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT,
  qty INTEGER NOT NULL DEFAULT 0 CHECK(qty >= 0),
  reorder_point INTEGER NOT NULL DEFAULT 10,
  unit_cost REAL NOT NULL DEFAULT 0,
  unit_weight REAL NOT NULL DEFAULT 1.0,      -- kg, used by the weight sensors
  bin_id TEXT, supplier_id INTEGER REFERENCES suppliers(id));
CREATE TABLE IF NOT EXISTS movements(
  id INTEGER PRIMARY KEY, sku TEXT NOT NULL REFERENCES products(sku),
  delta INTEGER NOT NULL, reason TEXT, user TEXT, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_mov_sku_ts ON movements(sku, ts);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, bin_id TEXT, sku TEXT,
  kind TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, user TEXT, action TEXT, detail TEXT,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
"""

def connect(path=":memory:"):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
