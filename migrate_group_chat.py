import sqlite3

print("🔧 Bắt đầu migration phòng chat chung...")

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Kiểm tra xem bảng đã tồn tại chưa
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='group_chat_message'")
if cursor.fetchone():
    print("⚠️  Bảng group_chat_message đã tồn tại, bỏ qua migration!")
    conn.close()
    exit(0)

# Tạo bảng group_chat_message
cursor.execute('''
CREATE TABLE group_chat_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES teacher(id)
)
''')

conn.commit()
conn.close()

print("✅ Đã tạo bảng group_chat_message!")
print("📋 Phòng chat chung đã sẵn sàng!")
