import re
from datetime import datetime, timedelta
from database.db import get_cursor, DB_TYPE
from tools.mcp_tools import calendar_create_event, task_create, note_create

class OrderAgent:
    @staticmethod
    def create_order(order_no, customer, part_no, qty, due_date):
        with get_cursor() as cur:
            if DB_TYPE == "alloydb":
                cur.execute("SELECT id FROM orders WHERE order_no = %s", (order_no,))
            else:
                cur.execute("SELECT id FROM orders WHERE order_no = ?", (order_no,))
            if cur.fetchone():
                return {"error": "Order already exists"}
            if DB_TYPE == "alloydb":
                cur.execute("INSERT INTO orders (order_no, customer, part_no, quantity, due_date, status) VALUES (%s,%s,%s,%s,%s,%s)",
                            (order_no, customer, part_no, qty, due_date, "pending_planning"))
            else:
                cur.execute("INSERT INTO orders (order_no, customer, part_no, quantity, due_date, status) VALUES (?,?,?,?,?,?)",
                            (order_no, customer, part_no, qty, due_date, "pending_planning"))
            return {"order_no": order_no, "status": "created"}

class MaterialAgent:
    @staticmethod
    def check_stock(part_no, required_qty):
        with get_cursor() as cur:
            if DB_TYPE == "alloydb":
                cur.execute("SELECT stock_qty FROM inventory WHERE part_no = %s", (part_no,))
            else:
                cur.execute("SELECT stock_qty FROM inventory WHERE part_no = ?", (part_no,))
            row = cur.fetchone()
            if not row:
                return {"action": "order_new_material", "needed": required_qty}
            available = row["stock_qty"] if hasattr(row, "keys") else row[0]
            if available < required_qty:
                deficit = required_qty - available
                task_create(f"Purchase {deficit} units of {part_no}", "HIGH", due_date=(datetime.now()+timedelta(days=2)).isoformat())
                note_create(f"Material shortage for {part_no}: need {deficit} units", ["inventory"])
                return {"action": "purchase_created", "deficit": deficit}
            return {"action": "sufficient", "available": available}

class PlanningAgent:
    @staticmethod
    def plan_operations(part_no):
        templates = {
            "B-789": [("Laser cut", "Laser Cutter", 30), ("CNC bending", "CNC Press", 20), ("Quality check", "QC Station", 10)],
            "A-123": [("CNC milling", "CNC Press", 45), ("Deburring", "Manual", 15), ("Quality check", "QC Station", 10)],
        }
        return templates.get(part_no, [("Inspect", "QC Station", 15)])

class SchedulerAgent:
    @staticmethod
    def schedule(order_id, operations):
        scheduled = []
        base_date = datetime.now().replace(hour=8, minute=0, second=0)
        
        # First, get the order ID from the database using order_no (since order_id might be string)
        with get_cursor() as cur:
            if DB_TYPE == "alloydb":
                cur.execute("SELECT id FROM orders WHERE order_no = %s", (order_id,))
            else:
                cur.execute("SELECT id FROM orders WHERE order_no = ?", (order_id,))
            row = cur.fetchone()
            db_order_id = row["id"] if row else None
        
        for op_name, machine, duration in operations:
            start = base_date.isoformat()
            end = (base_date + timedelta(minutes=duration)).isoformat()
            calendar_create_event(f"Order {order_id}: {op_name}", start, end, machine)
            scheduled.append({"operation": op_name, "machine": machine, "start": start, "end": end})
            
            # Insert into work_orders table for Gantt chart
            if db_order_id:
                with get_cursor() as cur:
                    if DB_TYPE == "alloydb":
                        cur.execute("""
                            INSERT INTO work_orders (order_id, operation, machine, start_time, end_time, status)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (db_order_id, op_name, machine, start, end, "scheduled"))
                    else:
                        cur.execute("""
                            INSERT INTO work_orders (order_id, operation, machine, start_time, end_time, status)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (db_order_id, op_name, machine, start, end, "scheduled"))
            
            base_date += timedelta(minutes=duration + 15)
        return scheduled

class ProductionAgent:
    @staticmethod
    def create_work_orders(order_id, schedule):
        for step in schedule:
            task_create(f"WO-{order_id}-{step['operation']}", "HIGH", assignee="Production Team", due_date=step['start'])
            note_create(f"Work order created for {step['operation']} on {step['machine']}", ["production"])

class DispatchAgent:
    @staticmethod
    def dispatch(order_no, invoice_no):
        with get_cursor() as cur:
            if DB_TYPE == "alloydb":
                cur.execute("UPDATE orders SET status = 'dispatched' WHERE order_no = %s", (order_no,))
                cur.execute("INSERT INTO dispatch_log (order_id, invoice_no, dispatched_at) VALUES ((SELECT id FROM orders WHERE order_no=%s), %s, %s)",
                            (order_no, invoice_no, datetime.now().isoformat()))
            else:
                cur.execute("UPDATE orders SET status = 'dispatched' WHERE order_no = ?", (order_no,))
                cur.execute("INSERT INTO dispatch_log (order_id, invoice_no, dispatched_at) VALUES ((SELECT id FROM orders WHERE order_no=?), ?, ?)",
                            (order_no, invoice_no, datetime.now().isoformat()))
        note_create(f"Invoice {invoice_no} generated for order {order_no}", ["dispatch"])
        return {"status": "dispatched", "invoice": invoice_no}

class PrimaryAgent:
    def __init__(self):
        self.order_agent = OrderAgent()
        self.material_agent = MaterialAgent()
        self.planning_agent = PlanningAgent()
        self.scheduler_agent = SchedulerAgent()
        self.production_agent = ProductionAgent()
        self.dispatch_agent = DispatchAgent()

    def process_command(self, user_input):
        lower = user_input.lower()
        if "new order" in lower or "create order" in lower:
            match_cust = re.search(r"from (\w+)", user_input)
            customer = match_cust.group(1) if match_cust else "Unknown"
            match_part = re.search(r"part (\w+-\d+)", user_input)
            part_no = match_part.group(1) if match_part else "B-789"
            match_qty = re.search(r"(\d+) units|(\d+) numbers", user_input)
            qty = int(match_qty.group(1) or match_qty.group(2)) if match_qty else 50
            match_date = re.search(r"due by (\w+ \d+)", user_input)
            due_date = match_date.group(1) if match_date else "2025-04-15"
            order_no = f"ORD-{datetime.now().strftime('%y%m%d%H%M%S')}"
            order_res = self.order_agent.create_order(order_no, customer, part_no, qty, due_date)
            if "error" in order_res:
                return order_res
            material = self.material_agent.check_stock(part_no, qty)
            ops = self.planning_agent.plan_operations(part_no)
            schedule = self.scheduler_agent.schedule(order_no, ops)
            self.production_agent.create_work_orders(order_no, schedule)
            note_create(f"Order {order_no} processed. Material: {material['action']}. Schedule created.", ["workflow"])
            return {"order_no": order_no, "material_check": material, "schedule": schedule, "message": f"Order {order_no} created and scheduled. Material action: {material['action']}"}
        elif "dispatch" in lower:
            match = re.search(r"order (\w+-\d+)", user_input)
            if not match:
                return {"error": "Please specify order number e.g., 'dispatch order ORD-105'"}
            order_no = match.group(1)
            invoice = f"INV-{order_no}"
            return self.dispatch_agent.dispatch(order_no, invoice)
        else:
            return {"message": "Command not recognized. Try 'new order from ...' or 'dispatch order ...'"}
