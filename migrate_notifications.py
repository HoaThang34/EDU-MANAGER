import sqlite3
import datetime

print("🔧 Bắt đầu migration hệ thống thông báo...")

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Kiểm tra xem bảng đã tồn tại chưa
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification'")
if cursor.fetchone():
    print("⚠️  Bảng notification đã tồn tại, bỏ qua migration!")
    conn.close()
    exit(0)

# Tạo bảng notification
cursor.execute('''
CREATE TABLE notification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    notification_type VARCHAR(50),
    target_role VARCHAR(50),
    is_read BOOLEAN DEFAULT 0,
    recipient_id INTEGER,
    FOREIGN KEY (created_by) REFERENCES teacher(id),
    FOREIGN KEY (recipient_id) REFERENCES teacher(id)
)
''')

conn.commit()
conn.close()

print("✅ Đã tạo bảng notification!")
print("📋 Hệ thống thông báo đã sẵn sàng!")
