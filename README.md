# 🎓 EduManager - Hệ Thống Quản Lý Giáo Dục Thông Minh

![EduManager Banner](https://img.shields.io/badge/EduManager-Smart%20Education-blue?style=for-the-badge&logo=googlescholar)
![Python](https://img.shields.io/badge/Python-3.8%2B-green?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-Web%20Framework-lightgrey?style=for-the-badge&logo=flask)
![AI](https://img.shields.io/badge/AI-Powered-purple?style=for-the-badge&logo=openai)

**EduManager** là một giải pháp quản lý học sinh hiện đại, được thiết kế để tối ưu hóa công việc của giáo viên chủ nhiệm và quản lý nhà trường. Với sự hỗ trợ mạnh mẽ từ trí tuệ nhân tạo (AI) local, hệ thống giúp tự động hóa việc theo dõi nề nếp, điểm số và phân tích dữ liệu học sinh một cách bảo mật và hiệu quả.

---

## ✨ Tính Năng Nổi Bật

### 🤖 Trợ Lý AI Chuyên Nghiệp (Ollama Based)
- **Chatbot Thông Minh**: Tra cứu thông tin học sinh, lịch sử vi phạm thông qua ngôn ngữ tự nhiên với khả năng ghi nhớ ngữ cảnh.
- **AI Analytics**: Tự động phân tích xu hướng nề nếp của lớp học và đưa ra nhận xét sư phạm chính xác.
- **Privacy First**: Toàn bộ dữ liệu AI được xử lý Local qua Ollama, bảo mật tuyệt đối thông tin học sinh.

### 🔍 Công Nghệ OCR Vision
- **Quét Thẻ Tự Động**: Nhận diện mã số học sinh từ ảnh chụp thẻ, giúp ghi nhận vi phạm nhanh chóng mà không cần nhập liệu thủ công.

### 📊 Quản Lý Toàn Diện
- **Bảng Điểm Đa Năng**: Quản lý điểm các môn học (TX, GK, HK) và tự động tính điểm trung bình, xuất học bạ.
- **Theo Dõi Nề Nếp**: Ghi nhận vi phạm, trừ điểm rèn luyện và theo dõi timeline tiến bộ của từng học sinh.
- **Báo Cáo Thông Minh**: Xuất báo cáo tuần, tháng, báo cáo phụ huynh và file Excel chỉ với một click.

---

## 🛠️ Stack Công Nghệ

| Thành phần | Công nghệ sử dụng |
| :--- | :--- |
| **Backend** | Python, Flask, SQLAlchemy |
| **Database** | SQLite (Local Storage) |
| **AI Engine** | Ollama, Gemini 3 Flash Preview (Cloud/Local Hybrid) |
| **Frontend** | HTML5, Tailwind CSS, Chart.js, FontAwesome |
| **Data Processing** | Pandas, OpenPyXL |

---

## 🚀 Hướng Dẫn Cài Đặt

### 1. Yêu cầu hệ thống
- Python 3.8+
- [Ollama](https://ollama.com) (Để chạy tính năng AI)

### 2. Cài đặt môi trường
```bash
# Clone dự án
git clone https://github.com/HoaThang34/EDU-MANAGER.git
cd EDU-MANAGER

# Cài đặt thư viện
pip install -r requirements.txt
```

### 3. Cấu hình AI (Ollama)
```bash
# Tải model AI
ollama pull gemini-3-flash-preview:cloud
```

### 4. Khởi tạo dữ liệu & Chạy ứng dụng
```bash
# Khởi tạo database (chỉ lần đầu)
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Chạy server
python app.py
```
Truy cập: `http://localhost:5000`

---

## 📂 Cá Cấu Trúc Thư Mục Chính

- `app.py`: Điều hướng logic và API chính của hệ thống.
- `models.py`: Định nghĩa cấu trúc cơ sở dữ liệu.
- `templates/`: Giao diện người dùng (Bố cục hiện đại với Tailwind CSS).
- `uploads/`: Lưu trữ tạm thời các file ảnh phục vụ OCR.

---

## 🔒 Bảo Mật & Quyền Riêng Tư

- Hệ thống hỗ trợ phân quyền giáo viên qua **Flask-Login**.
- Dữ liệu AI được xử lý local, đảm bảo không rò rỉ dữ liệu học sinh ra môi trường internet.
- Khuyến nghị đổi `SECRET_KEY` trong file `app.py` trước khi triển khai thực tế.

---

## 🤝 Đóng Góp & Phát Triển

Dự án được phát triển bởi đội ngũ học sinh **Trường THPT Chuyên Nguyễn Tất Thành**. Mọi ý kiến đóng góp vui lòng tạo Issue hoặc Pull Request trên GitHub.

---

**⭐ Nếu bạn thấy dự án hữu ích, hãy tặng chúng tôi 1 sao trên GitHub!**
