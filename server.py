from flask import Flask, request, jsonify
import os
from datetime import datetime
import sqlite3
from PIL import Image
import pytesseract

app = Flask(**name**)

# ============ Cấu hình nhẹ cho Render Free ============

UPLOAD_FOLDER = "/tmp/uploads"
DATABASE = "/tmp/smartgarage.db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ============ Khởi tạo DB ============

def get_db_connection():
conn = sqlite3.connect(DATABASE, check_same_thread=False)
conn.row_factory = sqlite3.Row
return conn

def init_db():
conn = get_db_connection()
c = conn.cursor()

```
c.execute('''
    CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate TEXT UNIQUE NOT NULL,
        owner TEXT
    )
''')
c.execute('''
    CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        esp_id TEXT NOT NULL,
        command TEXT NOT NULL,
        plate TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
''')
c.execute('''
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        esp_id TEXT,
        plate TEXT,
        ocr_text TEXT,
        matched INTEGER,
        note TEXT,
        ts TEXT NOT NULL
    )
''')
conn.commit()

# Nếu DB trống, thêm sẵn 1 xe demo
c.execute("SELECT COUNT(*) FROM vehicles")
if c.fetchone()[0] == 0:
    c.execute("INSERT INTO vehicles (plate, owner) VALUES (?,?)", ("ABC123", "DemoUser"))
    conn.commit()

conn.close()
```

# ============ OCR (dùng pytesseract, cực nhẹ) ============

def ocr_image(filepath):
img = Image.open(filepath)
text = pytesseract.image_to_string(img, lang='eng')
return text.strip()

# ============ API ============

@app.route('/')
def index():
return "✅ SmartGarage Flask (Render Free Edition) is running!"

# ESP upload ảnh để quét biển số

@app.route('/api/esp/upload', methods=['POST'])
def esp_upload():
try:
esp_id = request.form.get('esp_id') or request.args.get('esp_id')
if not esp_id:
return jsonify({"status": "error", "message": "Missing esp_id"}), 400

```
    file = request.files.get('image')
    if not file:
        return jsonify({"status": "error", "message": "No image received"}), 400

    filename = datetime.now().strftime(f"{esp_id}_%Y%m%d_%H%M%S.jpg")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    ocr_text = ocr_image(filepath)
    plate_detected = "".join(ocr_text.split()).upper()
    os.remove(filepath)  # Xóa ảnh để tiết kiệm RAM/disk

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM vehicles WHERE plate = ?", (plate_detected,))
    matched_row = c.fetchone()
    matched = 1 if matched_row else 0

    c.execute("INSERT INTO events (esp_id, plate, ocr_text, matched, note, ts) VALUES (?,?,?,?,?,?)",
              (esp_id, plate_detected, ocr_text, matched, "OCR processed", datetime.now().isoformat()))
    conn.commit()

    resp = {"status": "success", "esp_id": esp_id, "plate_text": plate_detected, "matched": bool(matched)}

    if matched:
        c.execute("INSERT INTO commands (esp_id, command, plate, status, created_at) VALUES (?,?,?,?,?)",
                  (esp_id, "OPEN", plate_detected, "pending", datetime.now().isoformat()))
        conn.commit()
        resp["command_created"] = "OPEN"

    conn.close()
    return jsonify(resp)

except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500
```

# ESP poll lệnh

@app.route('/api/esp/poll', methods=['GET'])
def esp_poll():
esp_id = request.args.get('esp_id')
if not esp_id:
return jsonify({"status": "error", "message": "Missing esp_id"}), 400

```
conn = get_db_connection()
c = conn.cursor()
c.execute("SELECT * FROM commands WHERE esp_id=? AND status='pending' ORDER BY created_at ASC LIMIT 1", (esp_id,))
cmd = c.fetchone()
if not cmd:
    conn.close()
    return jsonify({"status": "idle", "message": "No pending commands"})

c.execute("UPDATE commands SET status='sent' WHERE id=?", (cmd["id"],))
conn.commit()
conn.close()
return jsonify({"status": "ok", "command": cmd["command"], "plate": cmd["plate"], "cmd_id": cmd["id"]})
```

# ESP báo trạng thái thực thi

@app.route('/api/esp/status', methods=['POST'])
def esp_status():
data = request.get_json() or {}
esp_id = data.get("esp_id")
cmd_id = data.get("cmd_id")
result = data.get("result")

```
if not (esp_id and cmd_id and result):
    return jsonify({"status": "error", "message": "esp_id, cmd_id, result required"}), 400

conn = get_db_connection()
c = conn.cursor()
c.execute("UPDATE commands SET status=? WHERE id=? AND esp_id=?", (result, cmd_id, esp_id))
conn.commit()
c.execute("INSERT INTO events (esp_id, plate, ocr_text, matched, note, ts) VALUES (?,?,?,?,?,?)",
          (esp_id, None, None, 0, f"cmd_status:{result}", datetime.now().isoformat()))
conn.commit()
conn.close()
return jsonify({"status": "ok"})
```

# App Android gửi lệnh thủ công

@app.route('/api/app/command', methods=['POST'])
def app_command():
data = request.get_json() or {}
esp_id = data.get("esp_id")
command = (data.get("command") or "").upper()
plate = data.get("plate")

```
if not (esp_id and command):
    return jsonify({"status": "error", "message": "esp_id và command required"}), 400

conn = get_db_connection()
c = conn.cursor()
c.execute("INSERT INTO commands (esp_id, command, plate, status, created_at) VALUES (?,?,?,?,?)",
          (esp_id, command, plate, "pending", datetime.now().isoformat()))
conn.commit()
conn.close()
return jsonify({"status": "ok", "message": "Command queued"})
```

# Quản lý xe nhà

@app.route('/api/vehicles/add', methods=['POST'])
def add_vehicle():
data = request.get_json() or {}
plate = (data.get("plate") or "").upper().replace(" ", "")
if not plate:
return jsonify({"status": "error", "message": "plate required"}), 400

```
conn = get_db_connection()
c = conn.cursor()
try:
    c.execute("INSERT INTO vehicles (plate, owner) VALUES (?,?)", (plate, data.get("owner", "Unknown")))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "message": f"Added {plate}"})
except sqlite3.IntegrityError:
    conn.close()
    return jsonify({"status": "error", "message": "Plate already exists"}), 400
```

# App xác nhận mở cửa (ghi lịch sử vào DB)

@app.route('/api/app/confirm_open', methods=['POST'])
def app_confirm_open():
data = request.get_json() or {}
esp_id = data.get("esp_id")
plate = (data.get("plate") or "").upper()
approved = data.get("approved", False)

```
if not esp_id or not plate:
    return jsonify({"status": "error", "message": "esp_id và plate required"}), 400

conn = get_db_connection()
c = conn.cursor()

if approved:
    c.execute("INSERT INTO events (esp_id, plate, ocr_text, matched, note, ts) VALUES (?,?,?,?,?,?)",
              (esp_id, plate, None, 1, "App confirmed open", datetime.now().isoformat()))
    c.execute("INSERT INTO commands (esp_id, command, plate, status, created_at) VALUES (?,?,?,?,?)",
              (esp_id, "OPEN", plate, "pending", datetime.now().isoformat()))
    conn.commit()

conn.close()
return jsonify({"status": "ok", "approved": approved})
```

# Xem log lịch sử ra/vào

@app.route('/api/logs', methods=['GET'])
def get_logs():
conn = get_db_connection()
c = conn.cursor()
c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")
rows = [dict(r) for r in c.fetchall()]
conn.close()
return jsonify({"status": "ok", "logs": rows})

if **name** == "**main**":
init_db()
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
