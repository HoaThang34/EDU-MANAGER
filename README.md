# 🎓 EduManager - Hệ Thống Quản Lý Giáo Dục Thông Minh

![EduManager Banner](https://img.shields.io/badge/EduManager-Smart%20Education-blue?style=for-the-badge&logo=googlescholar)
![Python](https://img.shields.io/badge/Python-3.8%2B-green?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-Web%20Framework-lightgrey?style=for-the-badge&logo=flask)
![AI](https://img.shields.io/badge/AI-Powered-purple?style=for-the-badge&logo=openai)

**EduManager** là một giải pháp quản lý học sinh toàn diện, hiện đại, được thiết kế chuyên biệt để tối ưu hóa công việc của giáo viên chủ nhiệm và ban quản lý nhà trường. Tích hợp trí tuệ nhân tạo (AI) chạy local, EduManager giúp tự động hóa việc theo dõi nề nếp, quản lý điểm số và phân tích dữ liệu học sinh một cách bảo mật, chính xác và chuyên nghiệp.

---

## ✨ Tính Năng Nổi Bật

### 🤖 Trợ Lý AI Đa Năng (Hệ điều hành Ollama)
- **Chatbot Thông Minh**: Tương tác bằng ngôn ngữ tự nhiên để tra cứu thông tin học sinh, lịch sử vi phạm, và tư vấn sư phạm dựa trên ngữ cảnh thực tế.
- **Phân Tích Dữ Liệu AI**: Tự động tổng hợp xu hướng nề nếp của lớp, đưa ra những nhận xét sắc sảo và dự báo về sự tiến bộ của học sinh.
- **Bảo Mật Tuyệt Đối (Privacy First)**: Xử lý dữ liệu hoàn toàn Local thông qua Ollama, đảm bảo thông tin nhạy cảm của học sinh không bao giờ rời khỏi máy tính của bạn.

### 🔍 Công Nghệ OCR Vision Hiện Đại
- **Quét Thẻ Thông Minh**: Tự động nhận diện mã số học sinh từ ảnh chụp thẻ, giúp ghi nhận vi phạm nhanh chóng, giảm thiểu sai sót do nhập liệu thủ công.

### 📊 Hệ Thống Quản Lý Chuyên Sâu
- **Quản Lý Điểm Số**: Theo dõi điểm thành phần (TX, GK, HK), tự động tính điểm trung bình và xếp loại học lực theo quy định mới nhất.
- **Theo Dõi Nề Nếp & Điểm Thưởng**: Ghi nhận chi tiết các lỗi vi phạm và các điểm cộng (Bonus points), xây dựng timeline tiến bộ trực quan cho từng học sinh.
- **Báo Cáo Đa Dạng**: Xuất báo cáo tuần, tháng, báo cáo dành cho phụ huynh và tệp Excel chuyên nghiệp chỉ với một click.

### 📄 Trang Thông Tin & Pháp Lý
- **Tài liệu & Tính năng** (`/docs`): Giới thiệu chi tiết ứng dụng, tính năng chính, hướng ứng dụng thực tế và tầm nhìn phát triển.
- **Chính sách bảo mật** (`/privacy`): Cam kết thu thập, lưu trữ, sử dụng và bảo vệ dữ liệu; AI xử lý local, không gửi dữ liệu nhạy cảm lên internet.
- **Điều khoản sử dụng** (`/terms`): Quy định sử dụng, trách nhiệm tài khoản, quyền sở hữu dữ liệu và liên hệ.

### 👥 Phân Quyền & Giao Tiếp
- **Phân quyền**: Admin, Giáo viên chủ nhiệm (theo lớp), Giáo viên bộ môn (theo môn); quản lý giáo viên và gửi thông báo theo vai trò/lớp.
- **Tin nhắn & thông báo**: Phòng chat chung, tin nhắn riêng giáo viên–học sinh, thông báo theo lớp hoặc vai trò.
- **Học sinh**: Đăng nhập riêng, xem điểm rèn luyện, chat với giáo viên, nhận thông báo.

---

## 🛠️ Stack Công Nghệ

| Thành phần | Công nghệ sử dụng |
| :--- | :--- |
| **Hệ điều hành** | Python, Flask, SQLAlchemy |
| **Cơ sở dữ liệu** | SQLite (Local Storage) |
| **Công cụ AI** | Ollama, Gemini 3 Flash Preview (Cloud/Local Hybrid) |
| **Giao diện (Frontend)** | HTML5, Vanilla CSS, Chart.js, FontAwesome |
| **Xử lý dữ liệu** | Pandas, OpenPyXL |

---

## 🚀 Hướng Dẫn Cài Đặt

### 1. Yêu cầu hệ thống
- Python 3.8 trở lên.
- [Ollama](https://ollama.com) (Cần thiết cho các tính năng AI).

### 2. Cài đặt môi trường
```bash
# Clone dự án từ GitHub
git clone https://github.com/HoaThang34/EDU-MANAGER.git
cd EDU-MANAGER

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

### 3. Cấu hình AI (Ollama)
```bash
# Tải model AI phù hợp
ollama pull gemini-1.5-flash # Hoặc model bạn đang sử dụng
```

### 4. Khởi chạy ứng dụng
```bash
# Khởi tạo cơ sở dữ liệu (chỉ thực hiện lần đầu)
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Chạy server ứng dụng
python app.py
```
Sau khi khởi chạy thành công, truy cập: `http://localhost:5000`

---

## 📂 Cấu Trúc Thư Mục Chính

- `app.py`: Tệp tin điều hành chính, xử lý logic server và API.
- `models.py`: Định nghĩa cấu trúc các bảng trong cơ sở dữ liệu.
- `templates/`: Kho chứa giao diện người dùng (base, welcome, dashboard, docs, privacy, terms, ...).
- `uploads/`: Thư mục lưu trữ ảnh tạm thời để xử lý OCR.
- `prompts.py`: Quản lý các prompt dành cho hệ thống AI.

---

## 🔒 Bảo Mật & Quyền Riêng Tư

- Quản lý truy cập an toàn với **Flask-Login**.
- Cam kết bảo mật: Dữ liệu AI được xử lý ngoại tuyến (offline), ngăn chặn mọi nguy cơ rò rỉ dữ liệu học sinh ra internet.
- **Lưu ý**: Hãy đảm bảo bạn đã cấu hình `SECRET_KEY` an toàn trong file `app.py` trước khi sử dụng.

---

## 🤝 Đóng Góp & Phát Triển

Dự án này được phát triển với niềm đam mê từ đội ngũ học sinh **Trường THPT Chuyên Nguyễn Tất Thành**. Chúng tôi luôn lắng nghe và trân trọng mọi ý kiến đóng góp. Vui lòng tạo Issue hoặc gửi Pull Request để cùng chúng tôi hoàn thiện sản phẩm.

---

**⭐ Nếu bạn yêu thích dự án này, hãy tặng chúng tôi 1 sao trên GitHub nhé!**
