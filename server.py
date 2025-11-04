from flask import Flask, request, jsonify
import os
from datetime import datetime
import sqlite3
from PIL import Image
import pytesseract

app = Flask(__name__)

# ============ Cấu hình cho Render Free ============

UPLOAD_FOLDER = "/tmp/uploads"
DATABASE = "/tmp/smartgarage.db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ============ Kết nối & khởi tạo DB ============

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

# Nếu DB trống, thêm sẵn danh sách 5 xe trong nhà
c.execute("SELECT COUNT(*) FROM vehicles")
if c.fetchone()[0] == 0:
    vehicles = [
        ("36A66666", "Thanh"),
        ("60B27272", "Vinh"),
        ("48C48484", "Tien"),
        ("62D62626", "Quoc"),
        ("69E69696", "Long")
    ]
    c.executemany("INSERT INTO vehicles (plate, owner) VALUES (?,?)", vehicles)
    conn.commit()

conn.close()
```

# ============ OCR bằng pytesseract ============

def ocr_image(filepath):
img = Image.open(filepath)
text = pytesseract.image_to_string(img, lang='eng')
return text.strip()

# ============ API chính ============

@app.route('/')
def index():
return "✅ SmartGarage Flask (Render Free Edition) is running!"

# ESP upload ảnh biển số để nhận diện

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
    os.remove(filepath)  # xóa ảnh sau khi xử lý để tiết kiệm dung lượng

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM vehicles WHERE plate = ?", (plate_detected,))
    matched_row = c.fetchone()
    matched = 1 if matched_row else 0

    # ⚠️ Không lưu lịch sử ra/vào ở đây — chỉ lưu sau khi App xác nhận
    c.execute("INSERT INTO events (esp_id, plate, ocr_text, matched, note, ts) VALUES (?,?,?,?,?,?)",
              (esp_id, plate_detected, ocr_text, matched, "OCR processed (waiting for app confirm)", datetime.now().isoformat()))
    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "esp_id": esp_id,
        "plate_text": plate_detected,
        "matched": bool(matched),
        "message": "OCR done, waiting for app confirmation"
    })
except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500
```

# App xác nhận mở cửa

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
    # Lưu lịch sử ra/vào khi App xác nhận
    c.execute("INSERT INTO events (esp_id, plate, ocr_text, matched, note, ts) VALUES (?,?,?,?,?,?)",
              (esp_id, plate, None, 1, "App confirmed open → Door opened", datetime.now().isoformat()))
    # Gửi lệnh mở cho ESP
    c.execute("INSERT INTO commands (esp_id, command, plate, status, created_at) VALUES (?,?,?,?,?)",
              (esp_id, "OPEN", plate, "pending", datetime.now().isoformat()))
    conn.commit()

conn.close()
return jsonify({"status": "ok", "approved": approved})
```

# ESP lấy lệnh từ server

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

# ESP gửi kết quả thực thi

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
c.execute("INSERT INTO events (esp_id, plate, ocr_text, matched, note, ts) VALUES (?,?,?,?,?,?)",
          (esp_id, None, None, 0, f"cmd_status:{result}", datetime.now().isoformat()))
conn.commit()
conn.close()
return jsonify({"status": "ok"})
```

# App thêm xe mới

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

# Xem lịch sử ra/vào

@app.route('/api/logs', methods=['GET'])
def get_logs():
conn = get_db_connection()
c = conn.cursor()
c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")
rows = [dict(r) for r in c.fetchall()]
conn.close()
return jsonify({"status": "ok", "logs": rows})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    print(f"SmartGarage Flask server is running on port {port}")
    app.run(host="0.0.0.0", port=port)
