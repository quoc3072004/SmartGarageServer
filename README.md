# SmartGarage Flask (Render Free Edition)

## Cài đặt


## API chính
- `POST /api/esp/upload` → ESP gửi ảnh, server OCR đọc biển số
- `POST /api/app/confirm_open` → App xác nhận mở cửa, lưu lịch sử
- `GET /api/logs` → Xem log xe ra/vào
- `GET /api/esp/poll` → ESP lấy lệnh
- `POST /api/esp/status` → ESP báo kết quả thực thi
