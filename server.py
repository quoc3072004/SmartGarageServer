from flask import Flask, request, jsonify
import os
import cv2
import easyocr
from datetime import datetime

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

reader = None  # chỉ load khi cần


@app.route('/')
def index():
    return "✅ SmartGarage Flask Server is running!"


@app.route('/api/ocr', methods=['POST'])
def ocr_plate():
    global reader
    try:
        if reader is None:
            print("🔄 Loading EasyOCR...")
            reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            print("✅ EasyOCR loaded")

        file = request.files.get('image')
        if not file:
            return jsonify({"status": "error", "message": "Không nhận được ảnh"}), 400

        filename = datetime.now().strftime("%Y%m%d_%H%M%S.jpg")
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        image = cv2.imread(filepath)
        if image is None:
            return jsonify({"status": "error", "message": "Không đọc được ảnh"}), 400

        result = reader.readtext(image)
        text = " ".join([res[1] for res in result]) if result else ""

        return jsonify({"status": "success", "filename": filename, "plate_text": text})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/test', methods=['GET'])
def test_connection():
    return jsonify({"message": "SmartGarage API online!"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
