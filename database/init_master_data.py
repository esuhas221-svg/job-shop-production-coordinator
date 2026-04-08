import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_cursor, init_db, DB_TYPE

def insert_master_data():
    init_db()
    with get_cursor() as cur:
        for table in ["dispatch_log", "work_orders", "orders", "inventory", "machines"]:
            cur.execute(f"DELETE FROM {table}")
        inv_data = [("A-123","Aluminum","3mm",150,50), ("B-789","Stainless Steel","5mm",20,30), ("C-456","Brass","2mm",80,20)]
        for inv in inv_data:
            if DB_TYPE == "alloydb":
                cur.execute("INSERT INTO inventory (part_no, material, thickness, stock_qty, reorder_level) VALUES (%s,%s,%s,%s,%s)", inv)
            else:
                cur.execute("INSERT INTO inventory (part_no, material, thickness, stock_qty, reorder_level) VALUES (?,?,?,?,?)", inv)
        machines = [("Laser Cutter","cutting"), ("CNC Press","bending"), ("QC Station","inspection")]
        for m in machines:
            if DB_TYPE == "alloydb":
                cur.execute("INSERT INTO machines (name, type) VALUES (%s,%s)", m)
            else:
                cur.execute("INSERT INTO machines (name, type) VALUES (?,?)", m)
        if DB_TYPE == "alloydb":
            cur.execute("INSERT INTO orders (order_no, customer, part_no, quantity, due_date, status) VALUES (%s,%s,%s,%s,%s,%s)",
                        ("ORD-105","ABC Corp","B-789",50,"2025-04-15","pending_planning"))
        else:
            cur.execute("INSERT INTO orders (order_no, customer, part_no, quantity, due_date, status) VALUES (?,?,?,?,?,?)",
                        ("ORD-105","ABC Corp","B-789",50,"2025-04-15","pending_planning"))
    print("✅ Master data inserted")

if __name__ == "__main__":
    insert_master_data()
