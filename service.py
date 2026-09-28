"""Core business logic: stock movements, reorder suggestions, users."""
import time
from .security import hash_password, verify_password, AuditLog

class InventoryError(Exception): pass

class InventoryService:
    def __init__(self, conn):
        self.conn, self.audit = conn, AuditLog(conn)

    # ---- users
    def create_user(self, username, password, role):
        h, s = hash_password(password)
        self.conn.execute("INSERT INTO users(username,pw_hash,salt,role) VALUES(?,?,?,?)", (username, h, s, role))
        self.audit.record("system", "create_user", f"{username}:{role}")
        self.conn.commit()

    def authenticate(self, username, password):
        r = self.conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if r and verify_password(password, r["pw_hash"], r["salt"]):
            return r["role"]
        self.audit.record(username, "login_failed", "")
        self.conn.commit()
        return None

    # ---- catalogue
    def add_supplier(self, name, lead_days=7):
        cur = self.conn.execute("INSERT INTO suppliers(name,lead_days) VALUES(?,?)", (name, lead_days))
        self.conn.commit()
        return cur.lastrowid

    def add_product(self, sku, name, category="", qty=0, reorder_point=10,
                    unit_cost=0.0, unit_weight=1.0, bin_id=None, supplier_id=None, user="system"):
        self.conn.execute("INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?)",
            (sku, name, category, qty, reorder_point, unit_cost, unit_weight, bin_id, supplier_id))
        self.audit.record(user, "add_product", f"{sku} qty={qty}")
        self.conn.commit()

    def get(self, sku):
        r = self.conn.execute("SELECT * FROM products WHERE sku=?", (sku,)).fetchone()
        if not r: raise InventoryError(f"unknown SKU {sku}")
        return dict(r)

    def list_products(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM products ORDER BY sku")]

    # ---- stock movement: atomic; qty never negative (CHECK + explicit guard)
    def adjust_stock(self, sku, delta, reason="", user="system", ts=None):
        p = self.get(sku)
        if p["qty"] + delta < 0:
            raise InventoryError(f"insufficient stock for {sku}: have {p['qty']}, change {delta}")
        try:
            self.conn.execute("UPDATE products SET qty = qty + ? WHERE sku=?", (delta, sku))
            self.conn.execute("INSERT INTO movements(sku,delta,reason,user,ts) VALUES(?,?,?,?,?)",
                              (sku, delta, reason, user, ts or time.time()))
            self.audit.record(user, "adjust_stock", f"{sku} {delta:+d} ({reason})")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.get(sku)["qty"]

    # ---- reporting
    def low_stock(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM products WHERE qty <= reorder_point ORDER BY qty - reorder_point")]

    def daily_demand(self, sku, days=30, now=None):
        now = now or time.time()
        r = self.conn.execute("SELECT COALESCE(SUM(-delta),0) AS out FROM movements "
                              "WHERE sku=? AND delta<0 AND ts>=?", (sku, now - days * 86400)).fetchone()
        return r["out"] / days

    def reorder_suggestions(self, safety_days=3, now=None):
        """Reorder point logic: order when stock < demand*(lead time + safety); qty to cover 30 days."""
        out = []
        for p in self.list_products():
            lead = 7
            if p["supplier_id"]:
                lead = self.conn.execute("SELECT lead_days FROM suppliers WHERE id=?",
                                         (p["supplier_id"],)).fetchone()["lead_days"]
            d = self.daily_demand(p["sku"], now=now)
            dynamic_rop = max(p["reorder_point"], d * (lead + safety_days))
            if p["qty"] <= dynamic_rop:
                target = d * 30 + d * safety_days
                out.append({"sku": p["sku"], "name": p["name"], "qty": p["qty"],
                            "daily_demand": round(d, 2), "days_of_cover": round(p["qty"] / d, 1) if d else None,
                            "order_qty": max(1, int(round(target - p["qty"])))})
        return sorted(out, key=lambda x: (x["days_of_cover"] is None, x["days_of_cover"] or 0))

    def stock_value(self):
        return self.conn.execute("SELECT COALESCE(SUM(qty*unit_cost),0) v FROM products").fetchone()["v"]
