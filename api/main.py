from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from agents.agents import PrimaryAgent
from database.db import get_cursor, init_db, DB_TYPE
from tools.mcp_tools import task_list, calendar_get_events, note_search, note_create, task_create
import json
from pathlib import Path
from datetime import datetime
import hashlib
import os

app = FastAPI(title="Job Shop Production Coordinator")
primary = PrimaryAgent()

class CommandRequest(BaseModel):
    text: str

class ProductionSimulation(BaseModel):
    order_id: int

@app.post("/agent/command")
async def agent_command(req: CommandRequest):
    result = primary.process_command(req.text)
    return result

@app.get("/orders")
async def list_orders():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM orders ORDER BY id DESC")
        rows = cur.fetchall()
        return [dict(row) for row in rows]

@app.get("/inventory")
async def get_inventory():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM inventory")
        rows = cur.fetchall()
        return [dict(row) for row in rows]

@app.get("/tasks")
async def get_tasks():
    return task_list()

@app.get("/calendar")
async def get_calendar():
    return calendar_get_events()

@app.get("/notes")
async def get_notes():
    notes_file = Path(__file__).parent.parent / "data" / "notes.json"
    if notes_file.exists():
        return json.loads(notes_file.read_text())
    return []

@app.post("/reset")
async def reset_system():
    with get_cursor() as cur:
        cur.execute("DELETE FROM orders")
        cur.execute("DELETE FROM work_orders")
        cur.execute("DELETE FROM dispatch_log")
        cur.execute("DELETE FROM inventory")
        inv_data = [("A-123","Aluminum","3mm",150,50), ("B-789","Stainless Steel","5mm",20,30), ("C-456","Brass","2mm",80,20)]
        for inv in inv_data:
            if os.getenv("DB_TYPE", "sqlite") == "alloydb":
                cur.execute("INSERT INTO inventory (part_no, material, thickness, stock_qty, reorder_level) VALUES (%s,%s,%s,%s,%s)", inv)
            else:
                cur.execute("INSERT INTO inventory (part_no, material, thickness, stock_qty, reorder_level) VALUES (?,?,?,?,?)", inv)
    data_dir = Path(__file__).parent.parent / "data"
    for fname in ["calendar.json", "tasks.json", "notes.json"]:
        (data_dir / fname).write_text("[]")
    return {"status": "reset complete"}

@app.get("/gantt_data")
async def gantt_data():
    with get_cursor() as cur:
        cur.execute("""
            SELECT w.machine, w.start_time, w.end_time, o.order_no, o.part_no, w.operation, w.order_id
            FROM work_orders w
            JOIN orders o ON w.order_id = o.id
            ORDER BY w.start_time
        """)
        rows = cur.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            color_hash = hashlib.md5(str(item['order_id']).encode()).hexdigest()[:6]
            item['color'] = f"#{color_hash}"
            result.append(item)
        return result

@app.post("/simulate_production_step")
async def simulate_production_step(sim: ProductionSimulation):
    with get_cursor() as cur:
        if os.getenv("DB_TYPE", "sqlite") == "alloydb":
            cur.execute("SELECT id, order_no, part_no, quantity, status FROM orders WHERE id = %s", (sim.order_id,))
        else:
            cur.execute("SELECT id, order_no, part_no, quantity, status FROM orders WHERE id = ?", (sim.order_id,))
        order = cur.fetchone()
        if not order:
            raise HTTPException(404, "Order not found")
        
        order_id = order["id"]
        order_no = order["order_no"]
        part_no = order["part_no"]
        current_qty = order["quantity"]
        
        if current_qty <= 0:
            return {"error": "Order already fully produced", "completed": True}
        
        if os.getenv("DB_TYPE", "sqlite") == "alloydb":
            cur.execute("SELECT stock_qty FROM inventory WHERE part_no = %s", (part_no,))
        else:
            cur.execute("SELECT stock_qty FROM inventory WHERE part_no = ?", (part_no,))
        stock_row = cur.fetchone()
        if not stock_row:
            return {"error": f"No inventory for {part_no}"}
        
        current_stock = stock_row["stock_qty"] if hasattr(stock_row, "keys") else stock_row[0]
        
        if current_stock <= 0:
            return {"error": f"Insufficient stock for {part_no}", "completed": False}
        
        new_stock = current_stock - 1
        if os.getenv("DB_TYPE", "sqlite") == "alloydb":
            cur.execute("UPDATE inventory SET stock_qty = %s WHERE part_no = %s", (new_stock, part_no))
        else:
            cur.execute("UPDATE inventory SET stock_qty = ? WHERE part_no = ?", (new_stock, part_no))
        
        new_qty = current_qty - 1
        new_status = "completed" if new_qty <= 0 else "in_production"
        if os.getenv("DB_TYPE", "sqlite") == "alloydb":
            cur.execute("UPDATE orders SET quantity = %s, status = %s WHERE id = %s", (new_qty, new_status, order_id))
        else:
            cur.execute("UPDATE orders SET quantity = ?, status = ? WHERE id = ?", (new_qty, new_status, order_id))
        
        note_create(f"Production: 1 unit of {part_no} (order {order_no}) completed. Stock: {new_stock}, Remaining: {new_qty}", ["production"])
        
        return {
            "order_id": order_id,
            "order_no": order_no,
            "part_no": part_no,
            "units_produced": 1,
            "new_stock": new_stock,
            "order_remaining_qty": new_qty,
            "order_status": new_status,
            "completed": new_qty <= 0
        }

@app.get("/earliest_scheduled_order")
async def earliest_scheduled_order():
    with get_cursor() as cur:
        cur.execute("""
            SELECT w.order_id, o.order_no, o.part_no, o.quantity, MIN(w.start_time) as earliest_start
            FROM work_orders w
            JOIN orders o ON w.order_id = o.id
            WHERE o.quantity > 0
            GROUP BY w.order_id
            ORDER BY earliest_start
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            return {"order_id": row["order_id"], "order_no": row["order_no"], "part_no": row["part_no"], "quantity": row["quantity"]}
        return None

@app.get("/plan_operations")
async def plan_operations(part_no: str):
    from agents.agents import PlanningAgent
    return PlanningAgent.plan_operations(part_no)

# ---------- Database Toggle Endpoints ----------
@app.post("/toggle_database")
async def toggle_database(request: dict = None):
    """Toggle between SQLite and AlloyDB"""
    if request is None:
        return {"error": "No request body"}
    db_type = request.get("db_type")
    if db_type not in ["sqlite", "alloydb"]:
        return {"error": "Invalid database type. Use 'sqlite' or 'alloydb'"}
    os.environ["DB_TYPE"] = db_type
    init_db()
    return {"status": "success", "db_type": db_type, "message": f"Switched to {db_type}"}
    os.environ["DB_TYPE"] = db_type
    init_db()
    return {"status": "success", "db_type": db_type, "message": f"Switched to {db_type}"}

@app.get("/current_db")
async def current_db():
    from database.db import DB_TYPE
    return {"db_type": DB_TYPE}

# ---------- HTML Dashboard ----------
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Precision Forge - Multi-Agent Production</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; font-family: system-ui, 'Segoe UI', Roboto, sans-serif; }
        body { margin: 0; padding: 20px; background: #f0f2f6; }
        .container { max-width: 1600px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .shop-name { background: linear-gradient(135deg, #0066cc, #004080); color: white; padding: 8px 20px; border-radius: 40px; }
        .control-bar { display: flex; gap: 15px; margin: 20px 0; flex-wrap: wrap; align-items: center; }
        button { background: #0066cc; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; }
        button:hover { background: #0052a3; }
        .reset-btn { background: #dc3545; }
        .reset-btn:hover { background: #bb2d3b; }
        .report-btn { background: #28a745; }
        .toggle-switch { display: flex; align-items: center; gap: 10px; background: white; padding: 5px 15px; border-radius: 30px; }
        .switch { position: relative; display: inline-block; width: 60px; height: 28px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; border-radius: 28px; }
        .slider:before { position: absolute; content: ""; height: 22px; width: 22px; left: 3px; bottom: 3px; background-color: white; border-radius: 50%; }
        input:checked + .slider { background-color: #0066cc; }
        input:checked + .slider:before { transform: translateX(32px); }
        .workflow { background: white; border-radius: 16px; padding: 20px; margin-bottom: 20px; }
        .agents { display: flex; justify-content: space-around; align-items: center; flex-wrap: wrap; gap: 10px; }
        .agent-node { text-align: center; padding: 15px 20px; background: #f8f9fa; border-radius: 12px; min-width: 100px; border: 2px solid #ddd; }
        .agent-node.glowing { box-shadow: 0 0 15px #0066cc; border-color: #0066cc; background: #e6f0ff; }
        .arrow { font-size: 24px; color: #0066cc; }
        .card { background: white; border-radius: 12px; padding: 15px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }
        .tabs { display: flex; gap: 10px; margin-bottom: 10px; }
        .tab { padding: 8px 16px; background: #e9ecef; border-radius: 20px; cursor: pointer; }
        .tab.active { background: #0066cc; color: white; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); justify-content: center; align-items: center; z-index: 1000; }
        .modal-content { background: white; padding: 20px; border-radius: 12px; width: 90%; max-width: 1200px; max-height: 80%; overflow: auto; }
        .close { float: right; cursor: pointer; font-size: 24px; }
        .gantt-container { overflow-x: auto; }
        .gantt-row { display: flex; margin-bottom: 20px; align-items: center; }
        .gantt-label { width: 150px; font-weight: bold; }
        .gantt-bars { flex: 1; position: relative; height: 50px; background: #f0f0f0; border-radius: 5px; }
        .gantt-bar { position: absolute; height: 40px; top: 5px; border-radius: 5px; color: white; padding: 5px; font-size: 12px; overflow: hidden; white-space: nowrap; display: flex; align-items: center; justify-content: center; }
        .factory { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 15px; margin: 20px 0; }
        .machine { background: #f8f9fa; border-radius: 12px; padding: 15px; text-align: center; flex: 1; min-width: 120px; border: 2px solid #ddd; transition: all 0.2s; }
        .machine.active { border-color: #28a745; background: #e6f7e6; transform: scale(1.02); }
        .part-counter { font-size: 24px; font-weight: bold; margin-top: 10px; }
        .part-ids { font-size: 10px; margin-top: 5px; color: #666; }
        .simulation-controls { margin-top: 20px; text-align: center; }
        .result-text { background: #e6f7e6; padding: 10px; border-radius: 8px; margin-top: 10px; display: none; }
        .speed-control { display: flex; align-items: center; gap: 10px; margin-left: 20px; }
        input[type="range"] { width: 150px; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div><h1>⚙️ Precision Forge & Machining</h1><p>Multi‑Agent AI Production Coordinator</p></div>
        <div class="shop-name">🏭 PRECISION FORGE</div>
    </div>
    <div class="control-bar">
        <div class="toggle-switch"><span>⚡ Real-time</span><label class="switch"><input type="checkbox" id="delayToggle"><span class="slider"></span></label><span>🐢 3s Delay</span></div>
        <div class="toggle-switch">
            <span>🗄️ DB:</span>
            <label class="switch">
                <input type="checkbox" id="dbToggle" onchange="toggleDatabase()">
                <span class="slider"></span>
            </label>
            <span id="dbStatus">SQLite</span>
        </div>
        <div class="speed-control">
            <span>🐌 Speed:</span>
            <input type="range" id="speedSlider" min="200" max="1500" value="600" step="50">
            <span id="speedValue">600</span><span>ms</span>
        </div>
        <button id="simulateFactoryBtn">🎬 Simulate Production (Factory View)</button>
        <button class="report-btn" id="ganttBtn">📊 Machine Loading Report (Gantt)</button>
        <button class="reset-btn" id="resetBtn">🔄 Reset Orders</button>
    </div>
    <div class="workflow">
        <h3>🤖 Agent Workflow</h3>
        <div class="agents" id="agentNodes">
            <div class="agent-node" data-agent="Primary">Primary<br><small>Orchestrator</small></div>
            <span class="arrow">→</span>
            <div class="agent-node" data-agent="Order">Order<br><small>DB CRUD</small></div>
            <span class="arrow">→</span>
            <div class="agent-node" data-agent="Material">Material<br><small>Inventory</small></div>
            <span class="arrow">→</span>
            <div class="agent-node" data-agent="Planning">Planning<br><small>BOM</small></div>
            <span class="arrow">→</span>
            <div class="agent-node" data-agent="Scheduler">Scheduler<br><small>Calendar</small></div>
            <span class="arrow">→</span>
            <div class="agent-node" data-agent="Production">Production<br><small>Work Orders</small></div>
            <span class="arrow">→</span>
            <div class="agent-node" data-agent="Dispatch">Dispatch<br><small>Shipping</small></div>
        </div>
    </div>
    <div class="card">
        <h3>📝 Agent Commander</h3>
        <input type="text" id="commandInput" style="width:70%; padding:10px;" placeholder="e.g., new order from ABC Corp: 50 units of part B-789 due by April 15">
        <button id="executeBtn">Execute Workflow</button>
        <div id="result" class="result-text"></div>
    </div>
    <div style="display:flex; gap:20px; flex-wrap:wrap;">
        <div class="card" style="flex:1;"><h3>📅 Calendar</h3><div id="calendarList">Loading...</div></div>
        <div class="card" style="flex:1;"><h3>✅ Tasks</h3><div id="tasksList">Loading...</div></div>
        <div class="card" style="flex:1;"><h3>📝 Notes</h3><div id="notesList">Loading...</div></div>
    </div>
    <div class="card">
        <div class="tabs"><div class="tab active" onclick="showTab('orders')">Orders</div><div class="tab" onclick="showTab('inventory')">Inventory</div></div>
        <div id="ordersTab" class="tab-content active"><div id="ordersTable">Loading...</div></div>
        <div id="inventoryTab" class="tab-content"><div id="inventoryTable">Loading...</div></div>
    </div>
</div>

<!-- Gantt Modal -->
<div id="ganttModal" class="modal">
    <div class="modal-content">
        <span class="close" onclick="closeGanttModal()">&times;</span>
        <h3>📊 Workstation vs. Date Gantt Chart</h3>
        <div id="ganttChart" class="gantt-container"></div>
    </div>
</div>

<!-- Factory Simulation Modal -->
<div id="factoryModal" class="modal">
    <div class="modal-content">
        <span class="close" onclick="closeFactoryModal()">&times;</span>
        <div id="factoryHeader" style="display:flex; justify-content:space-between;"><h3>🏭 Factory Floor Simulation - Continuous Flow</h3><div id="orderInfo" style="font-weight:bold;"></div></div>
        <div id="factoryLayout" class="factory"></div>
        <div class="simulation-controls">
            <button id="startSimulationBtn">▶ Start Production Run</button>
            <button id="pauseSimulationBtn">⏸ Pause</button>
            <button id="resetSimulationBtn">🔄 Reset</button>
        </div>
        <div id="simulationLog" style="margin-top:15px; background:#f0f2f6; padding:10px; border-radius:8px; height:150px; overflow-y:auto;"></div>
    </div>
</div>

<script>
    let simInterval = null;
    let currentOrder = null;
    let isSimulationRunning = false;
    let currentStepDelay = 600;
    
    let stations = {
        raw: [],
        laser: [],
        cncBend: [],
        cncPress: [],
        qc: [],
        completed: []
    };
    let nextPartId = 1;
    let remainingToProduce = 0;

    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
    
    function glowAgent(agentName) {
        document.querySelectorAll('.agent-node').forEach(node => {
            if (node.getAttribute('data-agent').toLowerCase() === agentName.toLowerCase()) {
                node.classList.add('glowing');
                setTimeout(() => node.classList.remove('glowing'), 800);
            }
        });
    }

    async function refreshData() {
        try {
            const [ordersRes, invRes, tasksRes, calRes, notesRes] = await Promise.all([
                fetch('/orders'), fetch('/inventory'), fetch('/tasks'), fetch('/calendar'), fetch('/notes')
            ]);
            const orders = await ordersRes.json();
            const inventory = await invRes.json();
            const tasks = await tasksRes.json();
            const calendar = await calRes.json();
            const notes = await notesRes.json();
            
            document.getElementById('ordersTable').innerHTML = renderOrders(orders);
            document.getElementById('inventoryTable').innerHTML = renderInventory(inventory);
            document.getElementById('tasksList').innerHTML = renderTasks(tasks);
            document.getElementById('calendarList').innerHTML = renderCalendar(calendar);
            document.getElementById('notesList').innerHTML = renderNotes(notes);
            
            return { orders, inventory };
        } catch(e) { console.error('Refresh error:', e); return null; }
    }

    function renderOrders(orders) {
        if(!orders.length) return 'No orders';
        return '<table><tr><th>ID</th><th>Order No</th><th>Customer</th><th>Part</th><th>Qty</th><th>Due</th><th>Status</th></tr>' +
            orders.map(o => `<tr><td>${o.id}</td><td>${o.order_no}</td><td>${o.customer}</td><td>${o.part_no}</td><td>${o.quantity}</td><td>${o.due_date}</td><td>${o.status}</td></tr>`).join('') + '</table>';
    }
    
    function renderInventory(inv) {
        if(!inv.length) return 'No inventory';
        return '<table><tr><th>Part</th><th>Material</th><th>Stock</th><th>Reorder</th></tr>' +
            inv.map(i => `<tr><td>${i.part_no}</td><td>${i.material}</td><td>${i.stock_qty}</td><td>${i.reorder_level}</td></tr>`).join('') + '</table>';
    }
    
    function renderTasks(tasks) {
        if(!tasks.length) return 'No tasks';
        return '<table><tr><th>Task</th><th>Priority</th><th>Status</th><th>Due</th></tr>' +
            tasks.map(t => `<tr><td>${t.title}</td><td>${t.priority}</td><td>${t.status}</td><td>${t.due_date || ''}</td></tr>`).join('') + '</table>';
    }
    
    function renderCalendar(events) {
        if(!events.length) return 'No events';
        return '<table><tr><th>Event</th><th>Start</th><th>End</th></tr>' +
            events.map(e => `<tr><td>${e.title}</td><td>${e.start}</td><td>${e.end}</td></tr>`).join('') + '</table>';
    }
    
    function renderNotes(notes) {
        if(!notes.length) return 'No notes';
        return '<ul>' + notes.slice(-8).map(n => `<li>${n.content.substring(0,100)}...</li>`).join('') + '</ul>';
    }

    async function sendCommandWithWorkflow() {
        const text = document.getElementById('commandInput').value.trim();
        if(!text) return;
        const resultDiv = document.getElementById('result');
        resultDiv.style.display = 'block';
        const useDelay = document.getElementById('delayToggle').checked;
        const delayMsFlow = useDelay ? 3000 : 100;
        let agents = text.toLowerCase().includes('new order') ? ['Primary','Order','Material','Planning','Scheduler','Production','Dispatch'] : ['Primary','Dispatch'];
        for(let ag of agents) {
            glowAgent(ag);
            resultDiv.innerHTML = `🤖 ${ag} agent working...`;
            await sleep(delayMsFlow);
        }
        resultDiv.innerHTML = '🚀 Executing...';
        const resp = await fetch('/agent/command', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text}) });
        const data = await resp.json();
        resultDiv.innerHTML = '<strong>Result:</strong><br>'+JSON.stringify(data,null,2);
        await refreshData();
        setTimeout(()=>resultDiv.style.display='none', 8000);
    }

    async function showGantt() {
        const res = await fetch('/gantt_data');
        const data = await res.json();
        if(!data.length) { document.getElementById('ganttChart').innerHTML = '<p>No work orders scheduled yet.</p>'; document.getElementById('ganttModal').style.display='flex'; return; }
        
        let machines = [...new Set(data.map(d=>d.machine))];
        let minTime = new Date(Math.min(...data.map(d=>new Date(d.start_time))));
        let maxTime = new Date(Math.max(...data.map(d=>new Date(d.end_time))));
        let timeRange = Math.max(1, (maxTime - minTime)/(1000*60*60));
        let widthPerHour = 100;
        let totalWidth = Math.max(900, timeRange * widthPerHour);
        
        let html = `<div style="min-width:${totalWidth}px;"><div style="margin-bottom:10px;"><strong>Legend:</strong> `;
        let uniqueOrders = [...new Set(data.map(d=>d.order_no))];
        uniqueOrders.forEach(order => {
            let color = data.find(d=>d.order_no===order).color;
            html += `<span style="display:inline-block; width:20px; height:20px; background:${color}; margin:0 5px;"></span>${order} `;
        });
        html += `</div>`;
        
        for(let machine of machines) {
            let jobs = data.filter(d=>d.machine===machine);
            html += `<div class="gantt-row"><div class="gantt-label">${machine}</div><div class="gantt-bars" style="position:relative; height:50px;">`;
            for(let job of jobs) {
                let start = new Date(job.start_time);
                let end = new Date(job.end_time);
                let left = ((start - minTime)/(1000*60*60)) * widthPerHour;
                let width = ((end - start)/(1000*60*60)) * widthPerHour;
                html += `<div class="gantt-bar" style="left:${left}px; width:${Math.max(width,40)}px; background:${job.color};" title="${job.order_no} - ${job.operation}">${job.order_no}<br><small>${job.operation}</small></div>`;
            }
            html += `</div></div>`;
        }
        html += '</div>';
        document.getElementById('ganttChart').innerHTML = html;
        document.getElementById('ganttModal').style.display = 'flex';
    }

    async function openFactorySimulation() {
        const res = await fetch('/earliest_scheduled_order');
        currentOrder = await res.json();
        if(!currentOrder) { alert('No scheduled orders found. Create a new order first.'); return; }
        
        await refreshData();
        const ordersRes = await fetch('/orders');
        const orders = await ordersRes.json();
        const orderData = orders.find(o => o.id === currentOrder.order_id);
        const currentQty = orderData ? orderData.quantity : currentOrder.quantity;
        
        document.getElementById('orderInfo').innerHTML = `Order: ${currentOrder.order_no} | Part: ${currentOrder.part_no} | Remaining: ${currentQty}`;
        
        stations = {
            raw: [],
            laser: [],
            cncBend: [],
            cncPress: [],
            qc: [],
            completed: []
        };
        
        for(let i = 1; i <= currentQty; i++) {
            stations.raw.push({ id: nextPartId++, orderNo: currentOrder.order_no, partNo: currentOrder.part_no });
        }
        remainingToProduce = currentQty;
        
        updateFactoryDisplay();
        document.getElementById('simulationLog').innerHTML = '';
        document.getElementById('factoryModal').style.display = 'flex';
    }

    function updateFactoryDisplay() {
        const stages = [
            { id: 'raw', label: 'Raw Material', parts: stations.raw },
            { id: 'laser', label: 'Laser Cutting', parts: stations.laser },
            { id: 'cncBend', label: 'CNC Bending', parts: stations.cncBend },
            { id: 'cncPress', label: 'CNC Press', parts: stations.cncPress },
            { id: 'qc', label: 'Quality Check', parts: stations.qc },
            { id: 'completed', label: 'Job Completed', parts: stations.completed }
        ];
        
        let html = '';
        for(let stage of stages) {
            let count = stage.parts.length;
            let partIds = stage.parts.map(p => p.id).join(',');
            html += `<div class="machine" id="machine-${stage.id}">
                        <div>${stage.label}</div>
                        <div class="part-counter">${count}</div>
                        <div class="part-ids">${partIds.substring(0,30)}${partIds.length>30?'...':''}</div>
                     </div>`;
        }
        document.getElementById('factoryLayout').innerHTML = html;
    }

    function addSimLog(msg) {
        const logDiv = document.getElementById('simulationLog');
        logDiv.innerHTML += `<div>${new Date().toLocaleTimeString()}: ${msg}</div>`;
        logDiv.scrollTop = logDiv.scrollHeight;
        if(logDiv.children.length > 50) {
            logDiv.removeChild(logDiv.children[0]);
        }
    }

    async function processProductionStep() {
        if(!isSimulationRunning) return;
        
        let moved = false;
        
        if(stations.qc.length > 0) {
            let completedPart = stations.qc.shift();
            stations.completed.push(completedPart);
            moved = true;
            addSimLog(`✅ ${completedPart.partNo} (${completedPart.orderNo}) - QC → Completed`);
            
            const resp = await fetch('/simulate_production_step', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({order_id: currentOrder.order_id})
            });
            const result = await resp.json();
            remainingToProduce = result.order_remaining_qty || remainingToProduce - 1;
            
            if(result.completed) {
                addSimLog(`🎉 Order ${currentOrder.order_no} FULLY COMPLETED! Total produced: ${stations.completed.length}`);
                if(simInterval) clearInterval(simInterval);
                isSimulationRunning = false;
                document.getElementById('startSimulationBtn').disabled = false;
            }
            await refreshData();
            document.getElementById('orderInfo').innerHTML = `Order: ${currentOrder.order_no} | Part: ${currentOrder.part_no} | Remaining: ${remainingToProduce}`;
        }
        else if(stations.cncPress.length > 0 && stations.qc.length < 5) {
            let part = stations.cncPress.shift();
            stations.qc.push(part);
            moved = true;
            addSimLog(`🔄 ${part.partNo} (${part.orderNo}) - CNC Press → Quality Check`);
            highlightMachine('qc');
        }
        else if(stations.cncBend.length > 0 && stations.cncPress.length < 5) {
            let part = stations.cncBend.shift();
            stations.cncPress.push(part);
            moved = true;
            addSimLog(`🔄 ${part.partNo} (${part.orderNo}) - CNC Bending → CNC Press`);
            highlightMachine('cncPress');
        }
        else if(stations.laser.length > 0 && stations.cncBend.length < 5) {
            let part = stations.laser.shift();
            stations.cncBend.push(part);
            moved = true;
            addSimLog(`🔄 ${part.partNo} (${part.orderNo}) - Laser Cutting → CNC Bending`);
            highlightMachine('cncBend');
        }
        else if(stations.raw.length > 0 && stations.laser.length < 3) {
            let part = stations.raw.shift();
            stations.laser.push(part);
            moved = true;
            addSimLog(`🔄 ${part.partNo} (${part.orderNo}) - Raw Material → Laser Cutting`);
            highlightMachine('laser');
        }
        
        if(moved) {
            updateFactoryDisplay();
        } else if(remainingToProduce <= 0 && stations.raw.length === 0 && stations.laser.length === 0 && 
                  stations.cncBend.length === 0 && stations.cncPress.length === 0 && stations.qc.length === 0) {
            if(simInterval) clearInterval(simInterval);
            isSimulationRunning = false;
            addSimLog(`🎉 All production complete! Total completed: ${stations.completed.length}`);
        }
    }

    function highlightMachine(machineId) {
        const machine = document.getElementById(`machine-${machineId}`);
        if(machine) {
            machine.classList.add('active');
            setTimeout(() => machine.classList.remove('active'), 500);
        }
    }

    function startSimulation() {
        if(simInterval) clearInterval(simInterval);
        isSimulationRunning = true;
        currentStepDelay = parseInt(document.getElementById('speedSlider').value);
        simInterval = setInterval(processProductionStep, currentStepDelay);
        addSimLog(`🚀 Production started - Continuous flow mode (${currentStepDelay}ms per step)`);
        document.getElementById('startSimulationBtn').disabled = true;
    }

    function pauseSimulation() {
        if(simInterval) {
            clearInterval(simInterval);
            simInterval = null;
            isSimulationRunning = false;
            addSimLog(`⏸ Production paused`);
            document.getElementById('startSimulationBtn').disabled = false;
        }
    }

    function resetSimulation() {
        if(simInterval) {
            clearInterval(simInterval);
            simInterval = null;
        }
        isSimulationRunning = false;
        stations = {
            raw: [],
            laser: [],
            cncBend: [],
            cncPress: [],
            qc: [],
            completed: []
        };
        for(let i = 1; i <= remainingToProduce; i++) {
            stations.raw.push({ id: nextPartId++, orderNo: currentOrder.order_no, partNo: currentOrder.part_no });
        }
        updateFactoryDisplay();
        addSimLog(`🔄 Simulation reset - ${remainingToProduce} units remaining in raw material`);
        document.getElementById('startSimulationBtn').disabled = false;
    }

    async function resetSystem() {
        if(confirm('Delete all orders and start fresh? This will keep inventory stock.')) {
            await fetch('/reset', {method:'POST'});
            await refreshData();
            alert('System reset complete - all orders cleared');
        }
    }

    // Database toggle functions
    async function toggleDatabase() {
        const toggle = document.getElementById('dbToggle');
        const dbStatus = document.getElementById('dbStatus');
        const newDb = toggle.checked ? 'alloydb' : 'sqlite';
        dbStatus.innerText = 'Switching...';
        try {
            const response = await fetch('/toggle_database', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({db_type: newDb})
            });
            const result = await response.json();
            if (result.status === 'success') {
                dbStatus.innerText = newDb === 'alloydb' ? 'AlloyDB' : 'SQLite';
                alert(`Switched to ${newDb}. Please refresh data.`);
                await refreshData();
            } else {
                dbStatus.innerText = 'Error';
                alert(result.error);
            }
        } catch(e) {
            dbStatus.innerText = 'Error';
            alert('Failed to toggle database: ' + e.message);
        }
    }

    async function checkCurrentDB() {
        try {
            const response = await fetch('/current_db');
            const data = await response.json();
            const toggle = document.getElementById('dbToggle');
            const dbStatus = document.getElementById('dbStatus');
            if (toggle) {
                toggle.checked = data.db_type === 'alloydb';
                dbStatus.innerText = data.db_type === 'alloydb' ? 'AlloyDB' : 'SQLite';
            }
        } catch(e) {
            console.error('Failed to get current DB:', e);
        }
    }

    function showTab(tab) {
        document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));
        if(tab==='orders') { document.querySelector('.tab').classList.add('active'); document.getElementById('ordersTab').classList.add('active'); }
        else { document.querySelectorAll('.tab')[1].classList.add('active'); document.getElementById('inventoryTab').classList.add('active'); }
    }
    
    function closeGanttModal() { document.getElementById('ganttModal').style.display = 'none'; }
    function closeFactoryModal() { if(simInterval) clearInterval(simInterval); isSimulationRunning = false; document.getElementById('factoryModal').style.display = 'none'; }

    // Speed slider
    document.getElementById('speedSlider').oninput = function() {
        currentStepDelay = parseInt(this.value);
        document.getElementById('speedValue').innerText = currentStepDelay;
        if(isSimulationRunning && simInterval) {
            clearInterval(simInterval);
            simInterval = setInterval(processProductionStep, currentStepDelay);
        }
    };

    document.getElementById('executeBtn').onclick = sendCommandWithWorkflow;
    document.getElementById('ganttBtn').onclick = showGantt;
    document.getElementById('resetBtn').onclick = resetSystem;
    document.getElementById('simulateFactoryBtn').onclick = openFactorySimulation;
    document.getElementById('startSimulationBtn').onclick = startSimulation;
    document.getElementById('pauseSimulationBtn').onclick = pauseSimulation;
    document.getElementById('resetSimulationBtn').onclick = resetSimulation;

    window.addEventListener('load', () => {
        refreshData();
        checkCurrentDB();
    });
</script>
</body>
</html>
    """
