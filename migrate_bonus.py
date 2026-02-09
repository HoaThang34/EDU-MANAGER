"""
Migration script để tạo bảng BonusType và BonusRecord
Chạy: python migrate_bonus.py
"""
import os
import sys

# Thêm thư mục gốc vào path
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, basedir)

from app import app, db
from models import BonusType, BonusRecord

def migrate():
    with app.app_context():
        # Tạo bảng mới
        db.create_all()
        print("✅ Đã tạo bảng bonus_type và bonus_record!")
        
        # Thêm dữ liệu mẫu nếu chưa có
        if BonusType.query.count() == 0:
            sample_types = [
                BonusType(name="Giải Nhất HSG cấp Tỉnh", points_added=30, description="Học sinh giỏi cấp tỉnh - Giải Nhất"),
                BonusType(name="Giải Nhì HSG cấp Tỉnh", points_added=25, description="Học sinh giỏi cấp tỉnh - Giải Nhì"),
                BonusType(name="Giải Ba HSG cấp Tỉnh", points_added=20, description="Học sinh giỏi cấp tỉnh - Giải Ba"),
                BonusType(name="Giải Khuyến khích HSG", points_added=10, description="Học sinh giỏi - Giải Khuyến khích"),
                BonusType(name="Tiến bộ vượt bậc", points_added=15, description="Học sinh có sự tiến bộ rõ rệt trong học tập"),
                BonusType(name="Hoạt động văn nghệ", points_added=5, description="Tham gia tích cực các hoạt động văn hóa văn nghệ"),
                BonusType(name="Hoạt động thể thao", points_added=5, description="Tham gia tích cực các hoạt động thể dục thể thao"),
                BonusType(name="Hoạt động tình nguyện", points_added=10, description="Tham gia các hoạt động tình nguyện, công tác xã hội"),
                BonusType(name="Thành tích đặc biệt", points_added=20, description="Các thành tích xuất sắc khác"),
            ]
            
            for bt in sample_types:
                db.session.add(bt)
            
            db.session.commit()
            print(f"✅ Đã thêm {len(sample_types)} loại điểm cộng mẫu!")
        else:
            print("ℹ️ Đã có dữ liệu loại điểm cộng, bỏ qua thêm mẫu.")
        
        print("\n🎉 Migration hoàn tất!")

if __name__ == "__main__":
    migrate()
