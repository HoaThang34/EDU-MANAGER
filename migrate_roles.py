"""
Migration script để thêm các cột phân quyền vào bảng Teacher
Chạy: python migrate_roles.py
"""
import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

def migrate():
    print("🔧 Bắt đầu migration hệ thống phân quyền...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Kiểm tra các cột đã tồn tại chưa
    cursor.execute("PRAGMA table_info(teacher)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    print(f"📋 Các cột hiện có: {existing_columns}")
    
    new_columns = [
        ("role", "VARCHAR(20) DEFAULT 'homeroom_teacher'"),
        ("assigned_class", "VARCHAR(50)"),
        ("assigned_subject_id", "INTEGER"),
        ("created_by", "INTEGER"),
        ("created_at", "DATETIME")
    ]
    
    for col_name, col_def in new_columns:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE teacher ADD COLUMN {col_name} {col_def}")
                print(f"✅ Đã thêm cột: {col_name}")
            except sqlite3.OperationalError as e:
                print(f"⚠️ Lỗi khi thêm cột {col_name}: {e}")
        else:
            print(f"⏭️ Cột {col_name} đã tồn tại, bỏ qua")
    
    # Cập nhật tất cả tài khoản hiện tại thành admin
    cursor.execute("UPDATE teacher SET role = 'admin' WHERE role IS NULL OR role = 'homeroom_teacher'")
    updated_count = cursor.rowcount
    print(f"🔑 Đã cập nhật {updated_count} tài khoản hiện tại thành admin")
    
    # Cập nhật created_at cho các tài khoản chưa có
    current_time = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(f"UPDATE teacher SET created_at = '{current_time}' WHERE created_at IS NULL")
    
    conn.commit()
    conn.close()
    
    print("✨ Migration hoàn tất!")
    print("📌 Tất cả tài khoản hiện tại đã được nâng cấp lên quyền Admin")

if __name__ == "__main__":
    migrate()
