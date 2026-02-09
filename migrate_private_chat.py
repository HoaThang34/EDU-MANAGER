import sqlite3

print("🔧 Bắt đầu migration chat riêng tư...")

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Kiểm tra xem bảng đã tồn tại chưa
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='private_message'")
if cursor.fetchone():
    print("⚠️  Bảng private_message đã tồn tại, bỏ qua migration!")
    conn.close()
    exit(0)

# Tạo bảng private_message
cursor.execute('''
CREATE TABLE private_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT 0,
    FOREIGN KEY (sender_id) REFERENCES teacher(id),
    FOREIGN KEY (receiver_id) REFERENCES teacher(id)
)
''')

conn.commit()
conn.close()

print("✅ Đã tạo bảng private_message!")
print("📋 Chat riêng tư đã sẵn sàng!")
