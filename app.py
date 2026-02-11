
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import os
import json
import datetime
import base64
import requests
import re
import unicodedata
import uuid
from io import BytesIO
from flask import send_file
import pandas as pd
import ollama
from functools import wraps
import markdown

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc, or_, and_
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)

from models import db, Student, Violation, ViolationType, Teacher, SystemConfig, ClassRoom, WeeklyArchive, Subject, Grade, ChatConversation, BonusType, BonusRecord, Notification, GroupChatMessage, PrivateMessage, ChangeLog


# === HELPER FUNCTIONS CHO PHÂN QUYỀN ===

def admin_required(f):
    """Decorator yêu cầu quyền admin để truy cập route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Vui lòng đăng nhập!", "error")
            return redirect(url_for('login'))
        if current_user.role != 'admin':
            flash("Bạn không có quyền truy cập chức năng này!", "error")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def get_role_display(role):
    """Chuyển đổi role code thành tên hiển thị tiếng Việt"""
    role_map = {
        'admin': 'Quản trị viên',
        'homeroom_teacher': 'Giáo viên chủ nhiệm',
        'subject_teacher': 'Giáo viên bộ môn'
    }
    return role_map.get(role, 'Giáo viên')

def get_accessible_students():
    """
    Trả về query Student dựa trên role của current_user
    - Admin: Tất cả học sinh
    - GVCN: Chỉ học sinh lớp assigned_class
    - GVBM: Tất cả học sinh (để chấm điểm)
    """
    if not current_user.is_authenticated:
        return Student.query.filter(Student.id == -1)  # Empty query
    
    if current_user.role == 'admin':
        return Student.query
    elif current_user.role == 'homeroom_teacher' and current_user.assigned_class:
        return Student.query.filter_by(student_class=current_user.assigned_class)
    elif current_user.role == 'subject_teacher':
        return Student.query  # GVBM có thể xem tất cả HS để chấm điểm
    return Student.query.filter(Student.id == -1)  # Empty query

def can_access_student(student_id):
    """Kiểm tra quyền truy cập học sinh cụ thể"""
    if not current_user.is_authenticated:
        return False
    if current_user.role == 'admin':
        return True
    student = Student.query.get(student_id)
    if not student:
        return False
    if current_user.role == 'homeroom_teacher':
        return student.student_class == current_user.assigned_class
    if current_user.role == 'subject_teacher':
        return True  # GVBM có thể truy cập tất cả HS để chấm điểm
    return False


def call_ollama(prompt, model=None):
    """
    Gọi Ollama API để chat với AI model local.
    Model mặc định: gemini-3-flash-preview (chạy bằng: ollama run gemini-3-flash-preview)
    Args:
        prompt: Câu hỏi/prompt gửi cho AI
        model: Tên model Ollama (None = dùng OLLAMA_MODEL)
    Returns:
        (response_text, error)
    """
    model = model or OLLAMA_MODEL
    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response['message']['content'], None
    except Exception as e:
        return None, f"Lỗi kết nối Ollama: {str(e)}"

def can_access_subject(subject_id):
    """Kiểm tra quyền truy cập môn học"""
    if not current_user.is_authenticated:
        return False
    if current_user.role == 'admin':
        return True
    if current_user.role == 'subject_teacher':
        return current_user.assigned_subject_id == subject_id
    if current_user.role == 'homeroom_teacher':
        return True  # GVCN có thể xem tất cả môn
    return False

def create_notification(title, message, notification_type, target_role='all', specific_recipient_id=None):
    """
    Tạo thông báo mới
    - target_role: 'all', 'homeroom_teacher', 'subject_teacher', hoặc class name (VD: '12 Tin')
    - specific_recipient_id: Gửi cho 1 giáo viên cụ thể
    """
    if specific_recipient_id:
        # Gửi cho 1 người cụ thể
        notif = Notification(
            title=title,
            message=message,
            notification_type=notification_type,
            created_by=current_user.id if current_user.is_authenticated else None,
            recipient_id=specific_recipient_id,
            target_role=target_role
        )
        db.session.add(notif)
    else:
        # Broadcast: tạo notification cho mỗi giáo viên phù hợp
        if target_role == 'all':
            recipients = Teacher.query.all()
        elif target_role == 'homeroom_teacher':
            recipients = Teacher.query.filter_by(role='homeroom_teacher').all()
        elif target_role == 'subject_teacher':
            recipients = Teacher.query.filter_by(role='subject_teacher').all()
        else:
            # Target là class name -> chỉ gửi cho GVCN lớp đó
            recipients = Teacher.query.filter_by(role='homeroom_teacher', assigned_class=target_role).all()
        
        for recipient in recipients:
            if recipient.id != (current_user.id if current_user.is_authenticated else None):
                notif = Notification(
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    created_by=current_user.id if current_user.is_authenticated else None,
                    recipient_id=recipient.id,
                    target_role=target_role
                )
                db.session.add(notif)
    
    db.session.commit()


def log_change(change_type, description, student_id=None, student_name=None, student_class=None, old_value=None, new_value=None):
    """
    Ghi nhận thay đổi CSDL vào bảng ChangeLog.
    Gọi hàm này TRƯỚC db.session.commit() để đảm bảo cùng transaction.
    """
    try:
        changed_by_id = current_user.id if current_user.is_authenticated else None
        log_entry = ChangeLog(
            changed_by_id=changed_by_id,
            change_type=change_type,
            student_id=student_id,
            student_name=student_name,
            student_class=student_class,
            description=description,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None
        )
        db.session.add(log_entry)
    except Exception as e:
        print(f"ChangeLog Error: {e}")



basedir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(basedir, "templates")

app = Flask(__name__, template_folder=template_dir)

app.config["SECRET_KEY"] = "chia-khoa-bi-mat-cua-ban-ne-123456"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Ollama Configuration (model chạy bằng: ollama run gemini-3-flash-preview)
OLLAMA_MODEL = "gemini-3-flash-preview"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Vui lòng đăng nhập hệ thống."
login_manager.login_message_category = "error"

UPLOAD_FOLDER = os.path.join(basedir, "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Teacher, int(user_id))

@app.context_processor
def inject_global_data():
    try:
        week_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week = int(week_cfg.value) if week_cfg else 1
        classes = [c.name for c in ClassRoom.query.order_by(ClassRoom.name).all()]
    except:
        current_week = 1
        classes = []
    
    # Inject role info cho templates
    role_display = ''
    is_admin = False
    if current_user.is_authenticated:
        role_display = get_role_display(getattr(current_user, 'role', 'homeroom_teacher'))
        is_admin = getattr(current_user, 'role', None) == 'admin'
    
    return dict(
        current_week_number=current_week, 
        all_classes=classes,
        role_display=role_display,
        is_admin=is_admin
    )

@app.template_filter('markdown')
def markdown_filter(text):
    return markdown.markdown(text, extensions=['fenced_code', 'tables'])


def normalize_student_code(code):
    """
    Chuẩn hóa mã học sinh để tăng khả năng matching khi OCR đọc sai format
    
    Xử lý:
    - Bỏ dấu tiếng Việt (TOÁN → TOAN, Đạt → DAT)
    - Uppercase toàn bộ
    - Chuẩn hóa khoảng trắng (nhiều space → 1 space, trim đầu cuối)
    - Giữ nguyên dấu gạch ngang (-)
    
    Examples:
        "34 TOÁN - 001035" → "34 TOAN - 001035"
        "12  tin-001" → "12 TIN-001"
        "11a1  -  005" → "11A1 - 005"
        "Nguyễn Văn A" → "NGUYEN VAN A"
    
    Args:
        code (str): Mã học sinh cần chuẩn hóa
    
    Returns:
        str: Mã đã chuẩn hóa
    """
    if not code:
        return ""
    
    # 1. Bỏ dấu tiếng Việt bằng unicodedata
    code = unicodedata.normalize('NFD', str(code))
    code = ''.join(char for char in code if unicodedata.category(char) != 'Mn')
    
    # 2. Uppercase
    code = code.upper()
    
    # 3. Chuẩn hóa khoảng trắng: nhiều space → 1 space
    code = re.sub(r'\s+', ' ', code)
    
    # 4. Trim đầu cuối
    code = code.strip()
    
    return code


def get_current_iso_week():
    today = datetime.datetime.now()
    iso_year, iso_week, _ = today.isocalendar()
    return f"{iso_year}-W{iso_week}"

def format_date_vn(date_obj):
    return date_obj.strftime('%d/%m')

def save_weekly_archive(week_num):
    try:
        WeeklyArchive.query.filter_by(week_number=week_num).delete()
        students = Student.query.all()
        for s in students:
            deductions = db.session.query(func.sum(Violation.points_deducted))\
                .filter(Violation.student_id == s.id, Violation.week_number == week_num)\
                .scalar() or 0
            archive = WeeklyArchive(
                week_number=week_num, student_id=s.id, student_name=s.name,
                student_code=s.student_code, student_class=s.student_class,
                final_score=s.current_score, total_deductions=deductions
            )
            db.session.add(archive)
        db.session.commit()
        return True
    except Exception as e:
        print(f"Archive Error: {e}")
        db.session.rollback()
        return False

def is_reset_needed():
    """Kiểm tra xem đã sang tuần thực tế mới chưa để hiện cảnh báo"""
    try:
        current_iso_week = get_current_iso_week()
        last_reset_cfg = SystemConfig.query.filter_by(key="last_reset_week_id").first()
        
        # Nếu chưa từng reset lần nào -> Cần báo
        if not last_reset_cfg:
            return True
            
        # Nếu tuần thực tế khác tuần đã lưu -> Cần báo
        if current_iso_week != last_reset_cfg.value:
            return True
    except:
        pass
    return False

# === CHATBOT MEMORY HELPER FUNCTIONS ===

def get_or_create_chat_session():
    """
    Lấy session_id hiện tại từ Flask session hoặc tạo mới
    
    Returns:
        str: Session ID duy nhất cho cuộc hội thoại hiện tại
    """
    if 'chat_session_id' not in session:
        session['chat_session_id'] = str(uuid.uuid4())
    return session['chat_session_id']

def get_conversation_history(session_id, limit=10):
    """
    Lấy lịch sử hội thoại từ database
    
    Args:
        session_id (str): ID của chat session
        limit (int): Số lượng messages gần nhất (default 10)
    
    Returns:
        list[dict]: Danh sách messages theo format {"role": str, "content": str}
    """
    messages = ChatConversation.query.filter_by(
        session_id=session_id
    ).order_by(
        ChatConversation.created_at.asc()
    ).limit(limit).all()
    
    return [{"role": msg.role, "content": msg.message} for msg in messages]

def save_message(session_id, teacher_id, role, message, context_data=None):
    """
    Lưu message vào database
    
    Args:
        session_id (str): ID của session
        teacher_id (int): ID của teacher
        role (str): 'user' hoặc 'assistant'
        message (str): Nội dung message
        context_data (dict, optional): Metadata bổ sung (student_id, etc.)
    """
    chat_msg = ChatConversation(
        session_id=session_id,
        teacher_id=teacher_id,
        role=role,
        message=message,
        context_data=json.dumps(context_data) if context_data else None
    )
    db.session.add(chat_msg)
    db.session.commit()

# Context-aware AI System Prompt
CHATBOT_SYSTEM_PROMPT = """Vai trò: Bạn là một Trợ lý AI có Nhận thức Ngữ cảnh Cao (Context-Aware AI Assistant) cho giáo viên chủ nhiệm.

Mục tiêu: Duy trì sự liền mạch của cuộc hội thoại bằng cách ghi nhớ và sử dụng tích cực thông tin từ lịch sử trò chuyện.

Quy tắc Hoạt động:
1. Ghi nhớ Chủ động: Rà soát toàn bộ thông tin người dùng đã cung cấp trước đó (tên học sinh, yêu cầu, bối cảnh).
2. Tham chiếu Chéo: Lồng ghép chi tiết từ quá khứ để chứng minh bạn đang nhớ (VD: "Như bạn đã hỏi về em [tên] lúc nãy...").
3. Tránh Lặp lại: Không hỏi lại thông tin đã được cung cấp.
4. Cập nhật Trạng thái: Nếu người dùng thay đổi ý định, cập nhật ngay và xác nhận.

Định dạng Đầu ra: Phản hồi tự nhiên, ngắn gọn, thấu hiểu và luôn kết nối logic với các dữ kiện trước đó. Sử dụng emoji và markdown để dễ đọc.
"""

# === BULK VIOLATION IMPORT HELPER FUNCTIONS ===

def calculate_week_from_date(date_obj):
    """
    Calculate week_number from date
    Simple implementation: week of year
    
    Args:
        date_obj: datetime object
    
    Returns:
        int: week number
    """
    _, week_num, _ = date_obj.isocalendar()
    return week_num

def parse_excel_file(file):
    """
    Parse Excel file using pandas
    
    Expected columns:
    - Mã học sinh (student_code)
    - Loại vi phạm (violation_type_name)
    - Điểm trừ (points_deducted)
    - Ngày vi phạm (date_committed) - format: YYYY-MM-DD HH:MM or DD/MM/YYYY HH:MM
    - Tuần (week_number) - optional, auto-calculate if empty
    
    Returns:
        List[dict]: Violations data
    """
    try:
        df = pd.read_excel(file)
        
        # Validate required columns
        required_cols = ['Mã học sinh', 'Loại vi phạm', 'Điểm trừ', 'Ngày vi phạm']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Thiếu cột bắt buộc: {col}")
        
        violations = []
        for idx, row in df.iterrows():
            # Parse datetime
            date_str = str(row['Ngày vi phạm'])
            try:
                # Try YYYY-MM-DD HH:MM format
                date_committed = datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M')
            except:
                try:
                    # Try DD/MM/YYYY HH:MM format
                    date_committed = datetime.datetime.strptime(date_str, '%d/%m/%Y %H:%M')
                except:
                    try:
                        # Try date only YYYY-MM-DD
                        date_committed = datetime.datetime.strptime(date_str.split()[0], '%Y-%m-%d')
                    except:
                        raise ValueError(f"Dòng {idx+2}: Định dạng ngày không hợp lệ: {date_str}")
            
            # Calculate week_number if not provided
            week_number = row.get('Tuần', None)
            if pd.isna(week_number):
                week_number = calculate_week_from_date(date_committed)
            
            violations.append({
                'student_code': str(row['Mã học sinh']).strip(),
                'violation_type_name': str(row['Loại vi phạm']).strip(),
                'points_deducted': int(row['Điểm trừ']),
                'date_committed': date_committed,
                'week_number': int(week_number)
            })
        
        return violations
    except Exception as e:
        raise ValueError(f"Lỗi đọc file Excel: {str(e)}")

def import_violations_to_db(violations_data):
    """
    Import violations to database
    
    Args:
        violations_data: List[dict] with keys:
            - student_code
            - violation_type_name
            - points_deducted
            - date_committed
            - week_number
    
    Returns:
        Tuple[List[str], int]: (errors, success_count)
    """
    errors = []
    success_count = 0
    
    for idx, v_data in enumerate(violations_data):
        try:
            # 1. Tìm học sinh
            student = Student.query.filter_by(student_code=v_data['student_code']).first()
            if not student:
                errors.append(f"Dòng {idx+1}: Không tìm thấy học sinh '{v_data['student_code']}'")
                continue
            
            # 2. Lưu vào lịch sử vi phạm
            violation = Violation(
                student_id=student.id,
                violation_type_name=v_data['violation_type_name'],
                points_deducted=v_data['points_deducted'],
                date_committed=v_data['date_committed'],
                week_number=v_data['week_number']
            )
            
            db.session.add(violation)
            
            # 3. CẬP NHẬT TRỪ ĐIỂM NGAY LẬP TỨC (Đây là đoạn quan trọng mới thêm)
            current = student.current_score if student.current_score is not None else 100
            student.current_score = current - v_data['points_deducted']
            
            log_change('bulk_violation', f'Nhập vi phạm hàng loạt: {v_data["violation_type_name"]} (-{v_data["points_deducted"]} điểm)', student_id=student.id, student_name=student.name, student_class=student.student_class, old_value=current, new_value=student.current_score)
            
            success_count += 1
            
        except Exception as e:
            errors.append(f"Dòng {idx+1}: {str(e)}")
            db.session.rollback()
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        errors.append(f"Lỗi lưu database: {str(e)}")
    
    return errors, success_count

def _call_gemini(prompt, image_path=None, is_json=False):
    """
    Gọi Ollama local model để xử lý text hoặc vision tasks
    
    Args:
        prompt (str): Text prompt
        image_path (str, optional): Đường dẫn đến file ảnh
        is_json (bool): Yêu cầu response dạng JSON
    
    Returns:
        tuple: (response_text/dict, error_message)
    """
    try:
        # Prepare messages
        messages = []
        
        if image_path:
            # Vision task - sử dụng ollama.chat với images
            try:
                with open(image_path, "rb") as image_file:
                    image_data = base64.b64encode(image_file.read()).decode("utf-8")
                
                messages.append({
                    'role': 'user',
                    'content': prompt,
                    'images': [image_data]
                })
            except Exception as e:
                return None, f"Lỗi đọc file ảnh: {str(e)}"
        else:
            # Text-only task
            messages.append({
                'role': 'user',
                'content': prompt
            })
        
        # Prepare options
        options = {}
        if is_json:
            # Thêm instruction vào prompt để yêu cầu JSON format
            messages[0]['content'] = f"{prompt}\n\nIMPORTANT: Response MUST be valid JSON only, no additional text."
        
        # Call Ollama
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            options=options
        )
        
        # Extract response text
        if response and 'message' in response and 'content' in response['message']:
            text = response['message']['content'].strip()
            
            # Parse JSON if requested
            if is_json:
                try:
                    # Try to extract JSON from markdown code blocks if present
                    if '```json' in text:
                        json_start = text.find('```json') + 7
                        json_end = text.find('```', json_start)
                        text = text[json_start:json_end].strip()
                    elif '```' in text:
                        json_start = text.find('```') + 3
                        json_end = text.find('```', json_start)
                        text = text[json_start:json_end].strip()
                    
                    return json.loads(text), None
                except json.JSONDecodeError as e:
                    return None, f"Lỗi parse JSON: {str(e)}\nResponse: {text[:200]}"
            
            return text, None
        else:
            return None, "Không nhận được response từ Ollama"
            
    except Exception as e:
        return None, f"Lỗi kết nối Ollama: {str(e)}"


@app.route('/')
def welcome(): return render_template('welcome.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = Teacher.query.filter_by(username=request.form["username"]).first()
        if user and user.password == request.form["password"]:
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Sai thông tin đăng nhập!", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route('/scoreboard')
@login_required
def index():
    search = request.args.get('search', '').strip()
    selected_class = request.args.get('class_select', '').strip()
    q = get_accessible_students()  # Filter by role
    if selected_class: q = q.filter_by(student_class=selected_class)
    if search: q = q.filter(or_(Student.name.ilike(f"%{search}%"), Student.student_code.ilike(f"%{search}%")))
    students = q.order_by(Student.student_code.asc()).all()
    
    # Calculate GPA for each student
    week_cfg = SystemConfig.query.filter_by(key="current_week").first()
    current_week = int(week_cfg.value) if week_cfg else 1
    
    # Determine current semester and school year
    # Simple logic: weeks 1-20 = semester 1, weeks 21-40 = semester 2
    semester = 1 if current_week <= 20 else 2
    school_year = "2023-2024"  # Could be made dynamic later
    
    student_gpas = {}
    for student in students:
        gpa = calculate_student_gpa(student.id, semester, school_year)
        student_gpas[student.id] = gpa
    
    return render_template('index.html', students=students, student_gpas=student_gpas, search_query=search, selected_class=selected_class)

def calculate_student_gpa(student_id, semester, school_year):
    """
    Calculate GPA for a student
    Formula: (TX + GK*2 + HK*3) / 6 for each subject, then average all subjects
    
    Returns:
        float: GPA value (0.0 - 10.0) or None if no grades
    """
    grades = Grade.query.filter_by(
        student_id=student_id,
        semester=semester,
        school_year=school_year
    ).all()
    
    if not grades:
        return None
    
    # Group by subject
    grades_by_subject = {}
    for grade in grades:
        if grade.subject_id not in grades_by_subject:
            grades_by_subject[grade.subject_id] = {'TX': [], 'GK': [], 'HK': []}
        grades_by_subject[grade.subject_id][grade.grade_type].append(grade.score)
    
    # Calculate average for each subject
    subject_averages = []
    for subject_id, data in grades_by_subject.items():
        if data['TX'] and data['GK'] and data['HK']:
            avg_tx = sum(data['TX']) / len(data['TX'])
            avg_gk = sum(data['GK']) / len(data['GK'])
            avg_hk = sum(data['HK']) / len(data['HK'])
            subject_avg = round((avg_tx + avg_gk * 2 + avg_hk * 3) / 6, 2)
            subject_averages.append(subject_avg)
    
    if not subject_averages:
        return None
    
    # Calculate overall GPA
    gpa = round(sum(subject_averages) / len(subject_averages), 2)
    return gpa


@app.route("/dashboard")
@login_required
def dashboard():
    show_reset_warning = is_reset_needed()
    
    # 1. Lấy số thứ tự tuần hiện tại
    w_cfg = SystemConfig.query.filter_by(key="current_week").first()
    current_week = int(w_cfg.value) if w_cfg else 1
    
    s_class = request.args.get("class_select")
    
    # 2. Thống kê điểm số (Filter by role)
    # Nếu GVCN và không chọn lớp cụ thể, tự động filter assigned_class
    if not s_class and current_user.role == 'homeroom_teacher' and current_user.assigned_class:
        s_class = current_user.assigned_class
    
    q = get_accessible_students()  # Already filtered by role
    if s_class: 
        q = q.filter_by(student_class=s_class)
    c_tot = q.filter(Student.current_score >= 90).count()
    c_kha = q.filter(Student.current_score >= 70, Student.current_score < 90).count()
    c_tb = q.filter(Student.current_score < 70).count()
    
    # 3. Thống kê lỗi (CHỈ LẤY CỦA TUẦN HIỆN TẠI)
    vios_q = db.session.query(Violation.violation_type_name, func.count(Violation.violation_type_name).label("c"))
    
    # Lọc theo tuần hiện tại
    vios_q = vios_q.filter(Violation.week_number == current_week)
    
    if s_class: 
        vios_q = vios_q.join(Student).filter(Student.student_class == s_class)
        
    top = vios_q.group_by(Violation.violation_type_name).order_by(desc("c")).limit(5).all()
    
    return render_template("dashboard.html", 
                           show_reset_warning=show_reset_warning,
                           selected_class=s_class, 
                           pie_labels=json.dumps(["Tốt", "Khá", "Cần cố gắng"]), 
                           pie_data=json.dumps([c_tot, c_kha, c_tb]), 
                           bar_labels=json.dumps([n for n, _ in top]), 
                           bar_data=json.dumps([c for _, c in top]))


# === STUDENT PORTAL ROUTES ===

def student_required(f):
    """Decorator yêu cầu quyền học sinh để truy cập"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'student_id' not in session:
            return redirect(url_for('student_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        code = request.form.get("student_code", "").strip()
        # Chuẩn hóa mã
        norm_code = normalize_student_code(code)
        
        student = Student.query.filter_by(student_code=norm_code).first()
        if student:
            session['student_id'] = student.id
            session['student_name'] = student.name
            return redirect(url_for('student_dashboard'))
        else:
            flash("Mã học sinh không tồn tại! Vui lòng kiểm tra lại.", "error")
            
    return render_template("student_login.html")

@app.route("/student/logout")
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    return redirect(url_for('student_login'))

def get_student_ai_advice(student):
    """
    Phân tích dữ liệu học sinh và đưa ra lời khuyên từ AI
    """
    try:
        # 1. Lấy dữ liệu
        import prompts
        
        # Lấy vi phạm tuần hiện tại
        week_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week = int(week_cfg.value) if week_cfg else 1
        
        violations = Violation.query.filter_by(
            student_id=student.id, 
            week_number=current_week
        ).all()
        violation_text = ", ".join([v.violation_type_name for v in violations]) if violations else "Không có"
        
        # Lấy điểm cộng
        bonuses = BonusRecord.query.filter_by(
            student_id=student.id,
            week_number=current_week
        ).all()
        bonus_text = ", ".join([b.bonus_type_name for b in bonuses]) if bonuses else "Không có"
        
        # Lấy GPA (tạm tính HK hiện tại)
        semester = 1 if current_week <= 20 else 2
        gpa = calculate_student_gpa(student.id, semester, "2023-2024")
        gpa_text = str(gpa) if gpa else "Chưa có"
        
        # 2. Tạo prompt
        prompt = prompts.STUDENT_ANALYSIS_PROMPT.format(
            name=student.name,
            student_class=student.student_class,
            score=student.current_score,
            violations=violation_text,
            bonuses=bonus_text,
            gpa=gpa_text
        )
        
        # 3. Gọi AI
        advice, err = call_ollama(prompt)
        return advice if not err else "Hệ thống đang bận, em quay lại sau nhé!"
        
    except Exception as e:
        print(f"AI Advice Error: {e}")
        return "Chào em, chúc em một ngày học tập thật tốt! (Hệ thống tư vấn đang bảo trì)"

@app.route("/student/dashboard")
@student_required
def student_dashboard():
    student_id = session['student_id']
    student = Student.query.get(student_id)
    if not student:
        return redirect(url_for('student_logout'))
        
    # Lấy dữ liệu hiển thị
    week_cfg = SystemConfig.query.filter_by(key="current_week").first()
    current_week = int(week_cfg.value) if week_cfg else 1
    
    # 1. Vi phạm tuần này
    current_violations = Violation.query.filter_by(
        student_id=student_id, 
        week_number=current_week
    ).all()
    
    # 2. Điểm cộng tuần này
    current_bonuses = BonusRecord.query.filter_by(
        student_id=student_id,
        week_number=current_week
    ).all()
    
    # 3. Điểm số các môn (GPA)
    semester = 1 if current_week <= 20 else 2
    grades = Grade.query.filter_by(
        student_id=student_id,
        semester=semester
    ).all()
    
    # Group grades
    transcript = {}
    subjects = Subject.query.all()
    for sub in subjects:
        transcript[sub.name] = {'TX': [], 'GK': [], 'HK': [], 'TB': None}
        
    for g in grades:
        if g.subject.name in transcript:
            transcript[g.subject.name][g.grade_type].append(g.score)
            
    # Tính TB môn
    for sub_name, data in transcript.items():
        if data['TX'] and data['GK'] and data['HK']:
            avg = (sum(data['TX'])/len(data['TX']) + sum(data['GK'])/len(data['GK'])*2 + sum(data['HK'])/len(data['HK'])*3) / 6
            data['TB'] = round(avg, 2)
            
    # 4. Lấy lời khuyên AI (Optional - có thể load async)
    ai_advice = get_student_ai_advice(student)
    
    return render_template("student_dashboard.html", 
                           student=student, 
                           violations=current_violations,
                           bonuses=current_bonuses,
                           transcript=transcript,
                           ai_advice=ai_advice,
                           current_week=current_week)

ALLOWED_CHAT_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}


def _student_chat_call_ollama(system_prompt, history, user_message, image_base64=None):
    """
    Gọi Ollama cho student chat. Nếu có image_base64 thì dùng message có images.
    history: list of dict {role, content}
    """
    model = OLLAMA_MODEL
    # Build messages cho Ollama (có hỗ trợ images trong user message)
    messages = []
    # System context: gộp system + history vào prompt của user đầu (hoặc message riêng tùy model)
    context = f"{system_prompt}\n\nLịch sử trò chuyện:\n"
    for h in history:
        context += f"{h['role'].title()}: {h['content']}\n"
    context += f"\nUser: {user_message}\nAssistant:"
    if image_base64:
        messages.append({"role": "user", "content": context, "images": [image_base64]})
    else:
        messages.append({"role": "user", "content": context})
    try:
        response = ollama.chat(model=model, messages=messages)
        return (response.get("message") or {}).get("content", "").strip(), None
    except Exception as e:
        return None, str(e)


@app.route("/api/student/chat", methods=["POST"])
@student_required
def student_chat_api():
    """
    API Chatbot cho học sinh.
    Chấp nhận: application/json { "message", "mode" } hoặc multipart/form-data với message, mode, file (tùy chọn).
    """
    msg = ""
    mode = "rule"
    file_obj = None
    image_base64 = None
    attached_filename = None

    if request.content_type and "multipart/form-data" in request.content_type:
        msg = (request.form.get("message") or "").strip()
        mode = request.form.get("mode") or "rule"
        file_obj = request.files.get("file")
        if file_obj and file_obj.filename:
            ext = (file_obj.filename or "").rsplit(".", 1)[-1].lower()
            if ext not in ALLOWED_CHAT_EXTENSIONS:
                return jsonify({"error": "Định dạng file không hỗ trợ. Chỉ chấp nhận: " + ", ".join(ALLOWED_CHAT_EXTENSIONS)}), 400
            attached_filename = file_obj.filename
            data = file_obj.read()
            if ext in {"png", "jpg", "jpeg", "gif", "webp"}:
                image_base64 = base64.b64encode(data).decode("utf-8")
            # PDF có thể mở rộng sau (OCR hoặc text extraction)
    else:
        data = request.get_json() or {}
        msg = data.get("message", "").strip()
        mode = data.get("mode", "rule")

    if not msg and not attached_filename:
        return jsonify({"error": "Empty message"}), 400
    if not msg:
        msg = f"[Đã gửi file: {attached_filename}]"

    student_id = session["student_id"]
    session_id = get_or_create_chat_session()

    save_message(session_id, None, "user", msg, context_data={"student_id": student_id, "mode": mode, "attachment": attached_filename})

    import prompts
    system_prompt = prompts.STUDENT_LEARNING_PROMPT if mode == "study" else prompts.STUDENT_RULE_PROMPT
    history = get_conversation_history(session_id, limit=6)
    reply, err = _student_chat_call_ollama(system_prompt, history, msg, image_base64=image_base64)
    if err:
        reply = "Xin lỗi, hiện tại mình đang bị 'lag' xíu. Bạn hỏi lại sau nhé! 😿"
    save_message(session_id, None, "assistant", reply, context_data={"student_id": student_id, "mode": mode})
    return jsonify({"reply": reply})


@login_required
def analyze_class_stats():
    """
    API Phân tích tình hình nề nếp.
    - Có khả năng TỰ ĐỘNG chọn tuần hiện tại nếu không nhận được tham số.
    """
    try:
        data = request.get_json() or {} # Thêm or {} để tránh lỗi nếu data None
        s_class = data.get("class_name", "")
        
        # 1. Lấy tuần hiện tại của hệ thống (QUAN TRỌNG)
        sys_week_cfg = SystemConfig.query.filter_by(key="current_week").first()
        sys_week = int(sys_week_cfg.value) if sys_week_cfg else 1

        # 2. Xử lý tham số tuần từ Frontend
        weeks_input = data.get("weeks", [])
        
        # Hỗ trợ format cũ (single week)
        if not weeks_input and data.get("week"):
            weeks_input = [int(data.get("week"))]
            
        # --- SỬA LỖI TẠI ĐÂY: Logic Default ---
        # Nếu Frontend không gửi tuần nào (trường hợp Dashboard) -> Lấy tuần hiện tại
        if not weeks_input:
            weeks_input = [sys_week]
        # -------------------------------------

        # Sắp xếp tuần tăng dần
        weeks_input = sorted(list(set([int(w) for w in weeks_input]))) # set() để loại bỏ trùng lặp

        stats_summary = [] 

        # 3. Quét qua từng tuần để lấy số liệu
        for w in weeks_input:
            # Logic: Tuần nhỏ hơn tuần hệ thống là Lịch sử (Archive), ngược lại là Hiện tại (Student)
            is_history = (w < sys_week)
            
            # --- Lấy thống kê Điểm số & Sĩ số ---
            if is_history:
                # Lấy từ kho lưu trữ
                q = WeeklyArchive.query.filter_by(week_number=w)
                if s_class: q = q.filter_by(student_class=s_class)
                archives = q.all()
                
                total_students = len(archives)
                if total_students > 0:
                    avg_score = sum(a.final_score for a in archives) / total_students
                    c_tot = sum(1 for a in archives if a.final_score >= 90)
                    c_tb = sum(1 for a in archives if a.final_score < 70)
                else:
                    avg_score, c_tot, c_tb = 0, 0, 0
            else:
                # Lấy từ dữ liệu thực tế đang chạy
                q = Student.query
                if s_class: q = q.filter_by(student_class=s_class)
                students = q.all()
                
                total_students = len(students)
                if total_students > 0:
                    avg_score = sum(s.current_score for s in students) / total_students
                    c_tot = sum(1 for s in students if s.current_score >= 90)
                    c_tb = sum(1 for s in students if s.current_score < 70)
                else:
                    avg_score, c_tot, c_tb = 0, 0, 0

            # --- Lấy Top vi phạm ---
            vios_q = db.session.query(Violation.violation_type_name, func.count(Violation.violation_type_name).label("c"))
            vios_q = vios_q.filter(Violation.week_number == w)
            if s_class:
                vios_q = vios_q.join(Student).filter(Student.student_class == s_class)
            
            top_violations = vios_q.group_by(Violation.violation_type_name).order_by(desc("c")).limit(3).all()
            
            violations_text = ", ".join([f"{name} ({count})" for name, count in top_violations])
            if not violations_text: violations_text = "Không có vi phạm đáng kể"

            stats_summary.append(
                f"- TUẦN {w}: Điểm TB {avg_score:.1f}/100. (Tốt: {c_tot}, Yếu/TB: {c_tb}). Vi phạm chính: {violations_text}."
            )

        # 4. Tạo Prompt gửi AI
        context_name = f"Lớp {s_class}" if s_class else "Toàn Trường"
        data_context = "\n".join(stats_summary)
        
        # Nếu chỉ phân tích 1 tuần -> Dùng prompt nhận xét tình hình
        if len(weeks_input) == 1:
            prompt = f"""
            Đóng vai Trợ lý Giáo dục. Phân tích nề nếp {context_name} trong {weeks_input[0]}:
            {data_context}
            
            Yêu cầu: Nhận xét ngắn gọn (3-4 câu) về tình hình, chỉ ra điểm tốt/xấu và đưa ra 1 lời khuyên. Giọng văn sư phạm, xây dựng.
            """
        else:
            # Nếu phân tích nhiều tuần -> Dùng prompt so sánh sự tiến bộ
            prompt = f"""
            Đóng vai Trợ lý Giáo dục. Hãy phân tích SỰ TIẾN BỘ nề nếp của {context_name} qua các tuần:
            {data_context}

            Yêu cầu:
            1. Nhận xét xu hướng (Tốt lên/Đi xuống?).
            2. Chỉ ra sự thay đổi về các lỗi vi phạm (Lỗi nào giảm, lỗi nào tăng?).
            3. Kết luận ngắn gọn: Khen ngợi hoặc nhắc nhở.
            4. Viết đoạn văn khoảng 4-5 câu.
            """
        
        # Gọi AI
        analysis_text, error = _call_gemini(prompt)
        
        if error: 
            return jsonify({"error": error}), 500
            
        return jsonify({"analysis": analysis_text})

    except Exception as e:
        print(f"Analyze Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/add_violation", methods=["GET", "POST"])
@login_required
def add_violation():
    if request.method == "POST":
        # Get list of rule IDs (can be multiple)
        selected_rule_ids = request.form.getlist("rule_ids[]")
        
        # 1. Lấy danh sách ID học sinh từ Form (Dạng Select nhiều)
        selected_student_ids = request.form.getlist("student_ids[]")
        
        # 2. Lấy danh sách từ OCR (Dạng JSON nếu có)
        ocr_json = request.form.get("students_list")
        
        if not selected_rule_ids:
            flash("Vui lòng chọn ít nhất một lỗi vi phạm!", "error")
            return redirect(url_for("add_violation"))

        w_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week = int(w_cfg.value) if w_cfg else 1
        count = 0

        # Process each violation type
        for rule_id in selected_rule_ids:
            try:
                rule = db.session.get(ViolationType, int(rule_id))
            except:
                continue
            
            if not rule:
                continue

            # A. Xử lý danh sách từ Dropdown chọn tay
            if selected_student_ids:
                for s_id in selected_student_ids:
                    student = db.session.get(Student, int(s_id))
                    if student:
                        old_score = student.current_score or 100
                        student.current_score = old_score - rule.points_deducted
                        db.session.add(Violation(student_id=student.id, violation_type_name=rule.name, points_deducted=rule.points_deducted, week_number=current_week))
                        log_change('violation', f'Vi phạm: {rule.name} (-{rule.points_deducted} điểm)', student_id=student.id, student_name=student.name, student_class=student.student_class, old_value=old_score, new_value=student.current_score)
                        count += 1
            
            # B. Xử lý danh sách từ OCR (Áp dụng normalize)
            elif ocr_json:
                try:
                    student_codes = json.loads(ocr_json)
                    for code in student_codes:
                        if not code: continue
                        
                        # Tìm kiếm với normalized code
                        code_normalized = normalize_student_code(str(code).strip())
                        s = None
                        
                        # Thử exact match trước
                        s = Student.query.filter_by(student_code=str(code).strip().upper()).first()
                        
                        # Thử normalized match nếu không tìm thấy
                        if not s:
                            all_students = Student.query.all()
                            for student in all_students:
                                if normalize_student_code(student.student_code) == code_normalized:
                                    s = student
                                    break
                        
                        if s:
                            old_score = s.current_score or 100
                            s.current_score = old_score - rule.points_deducted
                            db.session.add(Violation(student_id=s.id, violation_type_name=rule.name, points_deducted=rule.points_deducted, week_number=current_week))
                            log_change('violation', f'Vi phạm (OCR): {rule.name} (-{rule.points_deducted} điểm)', student_id=s.id, student_name=s.name, student_class=s.student_class, old_value=old_score, new_value=s.current_score)
                            count += 1
                except Exception as e:
                    print(f"OCR Error: {e}")

        if count > 0:
            db.session.commit()
            
            # Tạo thông báo cho GVCN các lớp bị ảnh hưởng
            affected_classes = set()
            if selected_student_ids:
                for s_id in selected_student_ids:
                    student = db.session.get(Student, int(s_id))
                    if student and student.student_class:
                        affected_classes.add(student.student_class)
            
            for class_name in affected_classes:
                try:
                    create_notification(
                        title=f"⚠️ Vi phạm mới - Lớp {class_name}",
                        message=f"{current_user.full_name} đã ghi nhận {count} vi phạm cho học sinh lớp {class_name}",
                        notification_type='violation',
                        target_role=class_name
                    )
                except:
                    pass  # Không để lỗi notification làm gián đoạn chức năng chính
            
            flash(f"Đã ghi nhận {count} vi phạm (cho {len(selected_student_ids) if selected_student_ids else 'nhiều'} học sinh x {len(selected_rule_ids)} lỗi).", "success")
        else:
            flash("Chưa chọn học sinh nào hoặc xảy ra lỗi.", "error")
        
        return redirect(url_for("add_violation"))

    # GET: Truyền thêm danh sách học sinh để hiển thị trong Dropdown (filtered by role)
    students = get_accessible_students().order_by(Student.student_class, Student.name).all()
    return render_template("add_violation.html", rules=ViolationType.query.all(), students=students)



@app.route("/bulk_import_violations")
@login_required
def bulk_import_violations():
    """Display bulk import page"""
    students = Student.query.order_by(Student.student_class, Student.name).all()
    violation_types = ViolationType.query.all()
    return render_template("bulk_import_violations.html", 
                          students=students, 
                          violation_types=violation_types)

@app.route("/process_bulk_violations", methods=["POST"])
@login_required
def process_bulk_violations():
    """
    Process bulk violation import from either:
    - Manual form entry (JSON array from frontend)
    - Excel file upload
    """
    try:
        # Check source type
        excel_file = request.files.get('excel_file')
        manual_data = request.form.get('manual_violations_json')
        
        violations_to_import = []
        
        if excel_file and excel_file.filename:
            # Process Excel file
            violations_to_import = parse_excel_file(excel_file)
        elif manual_data:
            # Process manual JSON data
            violations_to_import = json.loads(manual_data)
            
            # Convert date strings to datetime objects
            for v in violations_to_import:
                if isinstance(v['date_committed'], str):
                    v['date_committed'] = datetime.datetime.strptime(v['date_committed'], '%Y-%m-%dT%H:%M')
                if 'week_number' not in v or v['week_number'] is None:
                    v['week_number'] = calculate_week_from_date(v['date_committed'])
        else:
            return jsonify({"status": "error", "message": "Không có dữ liệu để import"}), 400
        
        # Validate & Import
        errors, success_count = import_violations_to_db(violations_to_import)
        
        if errors:
            return jsonify({
                "status": "partial" if success_count > 0 else "error",
                "errors": errors,
                "success": success_count,
                "message": f"Đã import {success_count} vi phạm. Có {len(errors)} lỗi."
            })
        
        return jsonify({
            "status": "success",
            "count": success_count,
            "message": f"✅ Đã import thành công {success_count} vi phạm!"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download_violation_template")
@login_required
def download_violation_template():
    """Generate and download Excel template"""
    # Create sample template
    df = pd.DataFrame({
        'Mã học sinh': ['12TIN-001', '12TIN-002', '11A1-005'],
        'Loại vi phạm': ['Đi trễ', 'Không mặc đồng phục', 'Thiếu học liệu'],
        'Điểm trừ': [5, 10, 3],
        'Ngày vi phạm': ['2024-01-15 08:30', '2024-01-16 07:45', '2024-01-20 14:00'],
        'Tuần': [3, 3, 4]
    })
    
    # Save to BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Violations')
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='template_import_violations.xlsx'
    )


@app.route("/upload_ocr", methods=["POST"])
@login_required
def upload_ocr():
    """⚡ Đọc CHỈ MÃ HỌC SINH từ thẻ và tìm trực tiếp trong CSDL."""
    uploaded_files = request.files.getlist("files[]")
    if not uploaded_files: 
        return jsonify({"error": "Chưa chọn file."})

    results = []
    
    # ⚡ PROMPT NÂNG CẤP - Đọc mã học sinh với nhiều biến thể
    prompt = """
    Hãy đọc MÃ HỌC SINH từ thẻ trong ảnh này.
    
    Mã học sinh có thể có các dạng:
    - 12TIN-001, 11A1-005, 10B-023
    - 34 TOAN - 001035 hoặc 34 TOÁN - 001035 (có thể có hoặc không có dấu tiếng Việt)
    - Có thể có hoặc không có khoảng trắng
    - HS123, SV2024001
    
    Trả về JSON với format:
    {
        "student_code": "mã số học sinh"
    }
    
    Lưu ý QUAN TRỌNG:
    - CHỈ trích xuất mã số học sinh, KHÔNG cần tên hoặc lớp
    - Đọc CHÍNH XÁC những gì thấy trên thẻ, GIỮ NGUYÊN format (có dấu thì giữ dấu, có space thì giữ space)
    - Nếu không đọc được mã số, trả về chuỗi rỗng ""
    """

    for f in uploaded_files:
        if f.filename == '': 
            continue
            
        p = os.path.join(UPLOAD_FOLDER, f.filename)
        f.save(p)
        
        # Gọi AI Vision để đọc mã
        data, error = _call_gemini(prompt, image_path=p, is_json=True)
        
        # Xóa file tạm
        if os.path.exists(p): 
            os.remove(p)

        if data:
            # Lấy mã học sinh từ response (GIỮ NGUYÊN format gốc)
            ocr_code_raw = str(data.get("student_code", "")).strip()
            
            if ocr_code_raw:
                # ⚡ TÌM KIẾM 2 LẦN: Exact match → Normalized match
                student = None
                match_method = ""
                
                # Lần 1: Thử exact match (uppercase)
                student = Student.query.filter_by(student_code=ocr_code_raw.upper()).first()
                if student:
                    match_method = "Exact match (uppercase)"
                
                # Lần 2: Nếu không tìm thấy, thử normalized match
                if not student:
                    ocr_code_normalized = normalize_student_code(ocr_code_raw)
                    all_students = Student.query.all()
                    
                    for s in all_students:
                        if normalize_student_code(s.student_code) == ocr_code_normalized:
                            student = s
                            match_method = f"Normalized match (chuẩn hóa: '{ocr_code_normalized}')"
                            break
                
                if student:
                    # ✅ Tìm thấy học sinh
                    item = {
                        "file_name": f.filename,
                        "ocr_data": {
                            "code": ocr_code_raw,
                            "normalized": normalize_student_code(ocr_code_raw)
                        },
                        "found": True,
                        "confidence": 100 if "Exact" in match_method else 95,
                        "match_reasons": [match_method],
                        "db_info": {
                            "name": student.name,
                            "code": student.student_code,
                            "class": student.student_class
                        },
                        "alternatives": []
                    }
                else:
                    # ❌ Không tìm thấy trong CSDL
                    item = {
                        "file_name": f.filename,
                        "ocr_data": {
                            "code": ocr_code_raw,
                            "normalized": normalize_student_code(ocr_code_raw)
                        },
                        "found": False,
                        "db_info": None,
                        "error": f"Không tìm thấy học sinh có mã '{ocr_code_raw}' (hoặc '{normalize_student_code(ocr_code_raw)}') trong hệ thống"
                    }
            else:
                # AI không đọc được mã
                item = {
                    "file_name": f.filename,
                    "ocr_data": {
                        "code": ""
                    },
                    "found": False,
                    "db_info": None,
                    "error": "AI không nhận diện được mã học sinh trên thẻ"
                }
            
            results.append(item)
        else:
            # Lỗi gọi AI
            results.append({
                "file_name": f.filename, 
                "error": error or "Không đọc được thông tin từ thẻ"
            })

    return jsonify({"results": results})

@app.route("/batch_violation", methods=["POST"])
def batch_violation(): return redirect(url_for('add_violation'))


@app.route("/manage_students")
@login_required
def manage_students():
    # Lấy danh sách học sinh (filtered by role)
    students = get_accessible_students().order_by(Student.student_code.asc()).all()
    class_list = ClassRoom.query.order_by(ClassRoom.name).all()
    return render_template("manage_students.html", students=students, class_list=class_list)

@app.route("/add_student", methods=["POST"])
@login_required
def add_student():
    db.session.add(Student(name=request.form["student_name"], student_code=request.form["student_code"], student_class=request.form["student_class"]))
    db.session.commit()
    flash("Thêm học sinh thành công", "success")
    return redirect(url_for("manage_students"))

@app.route("/delete_student/<int:student_id>", methods=["POST"])
@login_required
def delete_student(student_id):
    s = db.session.get(Student, student_id)
    if s:
        Violation.query.filter_by(student_id=student_id).delete()
        db.session.delete(s)
        db.session.commit()
        flash("Đã xóa học sinh", "success")
    return redirect(url_for("manage_students"))

@app.route("/edit_student/<int:student_id>", methods=["GET", "POST"])
@login_required
def edit_student(student_id):
    s = db.session.get(Student, student_id)
    if not s:
        flash("Không tìm thấy học sinh", "error")
        return redirect(url_for("manage_students"))
        
    if request.method == "POST":
        s.name = request.form["student_name"]
        s.student_code = request.form["student_code"]
        s.student_class = request.form["student_class"]
        db.session.commit()
        flash("Cập nhật thành công", "success")
        return redirect(url_for("manage_students"))
        
    return render_template("edit_student.html", student=s)

@app.route("/add_class", methods=["POST"])
@login_required
def add_class():
    if not ClassRoom.query.filter_by(name=request.form["class_name"]).first():
        db.session.add(ClassRoom(name=request.form["class_name"]))
        db.session.commit()
    return redirect(url_for("manage_students"))
#chỉnh sửa lớp học

@app.route("/edit_class/<int:class_id>", methods=["POST"])
@login_required
def edit_class(class_id):
    """Đổi tên lớp và cập nhật lại lớp cho toàn bộ học sinh"""
    try:
        new_name = request.form.get("new_name", "").strip()
        if not new_name:
            flash("Tên lớp không được để trống!", "error")
            return redirect(url_for("manage_students"))

        # Tìm lớp cần sửa
        cls = db.session.get(ClassRoom, class_id)
        if cls:
            old_name = cls.name
            
            # 1. Cập nhật tên trong bảng ClassRoom
            cls.name = new_name
            
            # 2. Cập nhật lại tên lớp cho TẤT CẢ học sinh đang ở lớp cũ
            # (Logic quan trọng để đồng bộ dữ liệu)
            students_in_class = Student.query.filter_by(student_class=old_name).all()
            for s in students_in_class:
                s.student_class = new_name
                
            db.session.commit()
            flash(f"Đã đổi tên lớp '{old_name}' thành '{new_name}' và cập nhật {len(students_in_class)} học sinh.", "success")
        else:
            flash("Không tìm thấy lớp học!", "error")
            
    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi: {str(e)}", "error")
        
    return redirect(url_for("manage_students"))

@app.route("/delete_class/<int:class_id>", methods=["POST"])
@login_required
def delete_class(class_id):
    """Xóa lớp học"""
    try:
        cls = db.session.get(ClassRoom, class_id)
        if cls:
            # Kiểm tra an toàn: Chỉ cho xóa nếu lớp RỖNG (không có học sinh)
            student_count = Student.query.filter_by(student_class=cls.name).count()
            if student_count > 0:
                flash(f"Không thể xóa lớp '{cls.name}' vì đang có {student_count} học sinh. Hãy chuyển hoặc xóa học sinh trước.", "error")
            else:
                db.session.delete(cls)
                db.session.commit()
                flash(f"Đã xóa lớp {cls.name}", "success")
    except Exception as e:
        flash(f"Lỗi: {str(e)}", "error")
    return redirect(url_for("manage_students"))
@app.route("/manage_rules", methods=["GET", "POST"])
@login_required
def manage_rules():
    if request.method == "POST":
        db.session.add(ViolationType(name=request.form["rule_name"], points_deducted=int(request.form["points"])))
        db.session.commit()
        flash("Đã thêm lỗi vi phạm", "success")
        return redirect(url_for("manage_rules"))
    return render_template("manage_rules.html", rules=ViolationType.query.all())

@app.route("/delete_rule/<int:rule_id>", methods=["POST"])
@login_required
def delete_rule(rule_id):
    r = db.session.get(ViolationType, rule_id)
    if r: db.session.delete(r); db.session.commit()
    return redirect(url_for("manage_rules"))

@app.route("/edit_rule/<int:rule_id>", methods=["GET", "POST"])
@login_required
def edit_rule(rule_id):
    r = db.session.get(ViolationType, rule_id)
    if request.method == "POST":
        r.name = request.form["rule_name"]
        r.points_deducted = int(request.form["points"])
        db.session.commit()
        flash("Đã sửa lỗi vi phạm", "success")
        return redirect(url_for("manage_rules"))
    return render_template("edit_rule.html", rule=r)

@app.route("/chatbot")
@login_required
def chatbot():
    return render_template("chatbot.html")

@app.route("/api/chatbot", methods=["POST"])
@login_required
def api_chatbot():
    """Context-aware chatbot với conversation memory"""
    msg = (request.json.get("message") or "").strip()
    if not msg:
        return jsonify({"response": "Vui lòng nhập câu hỏi."})
    
    # 1. Get/Create chat session
    session_id = get_or_create_chat_session()
    teacher_id = current_user.id
    
    # 2. Load conversation history
    history = get_conversation_history(session_id, limit=10)
    
    # 3. Save user message to database
    save_message(session_id, teacher_id, "user", msg)
    
    # 4. Tìm kiếm học sinh từ CSDL
    # Detect class name from message (e.g., "11 Tin", "12A", etc.)
    class_filter = None
    import re
    class_pattern = re.search(r'lớp\s*(\d+\s*[A-Za-z]+\d*|\d+)', msg, re.IGNORECASE)
    if class_pattern:
        class_filter = class_pattern.group(1).strip()
    
    # Build query
    query = Student.query.filter(
        or_(
            Student.name.ilike(f"%{msg}%"), 
            Student.student_code.ilike(f"%{msg}%")
        )
    )
    
    # Add class filter if detected
    if class_filter:
        query = query.filter(Student.student_class.ilike(f"%{class_filter}%"))
    
    s_list = query.limit(10).all()
    
    # Nếu tìm thấy học sinh
    if s_list:
        # Nếu có nhiều kết quả - hiển thị danh sách để chọn
        if len(s_list) > 1:
            response = f"**Tìm thấy {len(s_list)} học sinh:**\n\n"
            buttons = []
            
            for s in s_list:
                response += f"• {s.name} ({s.student_code}) - Lớp {s.student_class}\n"
                buttons.append({
                    "label": f"{s.name} - {s.student_class}",
                    "payload": f"{s.name}"
                })
            
            response += "\n*Nhấn vào tên để xem chi tiết*"
            
            # Save bot response
            save_message(session_id, teacher_id, "assistant", response)
            
            return jsonify({"response": response.strip(), "buttons": buttons})
        
        # Nếu chỉ có 1 kết quả - sử dụng AI để phân tích
        student = s_list[0]
        
        # Thu thập dữ liệu từ CSDL
        week_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week = int(week_cfg.value) if week_cfg else 1
        semester = 1
        school_year = "2023-2024"
        
        # Lấy điểm học tập
        grades = Grade.query.filter_by(
            student_id=student.id,
            semester=semester,
            school_year=school_year
        ).all()
        
        grades_data = {}
        if grades:
            grades_by_subject = {}
            for grade in grades:
                if grade.subject_id not in grades_by_subject:
                    grades_by_subject[grade.subject_id] = {
                        'subject_name': grade.subject.name,
                        'TX': [],
                        'GK': [],
                        'HK': []
                    }
                grades_by_subject[grade.subject_id][grade.grade_type].append(grade.score)
            
            for subject_id, data in grades_by_subject.items():
                subject_name = data['subject_name']
                avg_score = None
                
                if data['TX'] and data['GK'] and data['HK']:
                    avg_tx = sum(data['TX']) / len(data['TX'])
                    avg_gk = sum(data['GK']) / len(data['GK'])
                    avg_hk = sum(data['HK']) / len(data['HK'])
                    avg_score = round((avg_tx + avg_gk * 2 + avg_hk * 3) / 6, 2)
                    
                    grades_data[subject_name] = {
                        'TX': round(avg_tx, 1),
                        'GK': round(avg_gk, 1),
                        'HK': round(avg_hk, 1),
                        'TB': avg_score
                    }
        
        # Lấy vi phạm
        violations = Violation.query.filter_by(student_id=student.id).order_by(Violation.date_committed.desc()).all()
        violations_data = []
        if violations:
            for v in violations[:5]:
                violations_data.append({
                    'type': v.violation_type_name,
                    'points': v.points_deducted,
                    'date': v.date_committed.strftime('%d/%m/%Y')
                })
        
        # Tạo response có cấu trúc
        response = f"**📊 Thông tin học sinh: {student.name}**\n\n"
        response += f"• **Mã số:** {student.student_code}\n"
        response += f"• **Lớp:** {student.student_class}\n"
        response += f"• **Điểm hành vi:** {student.current_score}/100\n\n"
        
        if grades_data:
            response += "**📚 Điểm học tập (HK1):**\n"
            for subject, scores in grades_data.items():
                response += f"• {subject}: TX={scores['TX']}, GK={scores['GK']}, HK={scores['HK']}, TB={scores['TB']}\n"
        else:
            response += "**📚 Điểm học tập:** Chưa có dữ liệu\n"
        
        if violations_data:
            response += f"\n**⚠️ Vi phạm:** {len(violations)} lần\n"
            response += "Chi tiết gần nhất:\n"
            for v in violations_data:
                response += f"• {v['date']}: {v['type']} (-{v['points']} điểm)\n"
        else:
            response += "\n**⚠️ Vi phạm:** Không có\n"
        
        save_message(session_id, teacher_id, "assistant", response)
        
        buttons = [
            {"label": "📊 Xem học bạ", "payload": f"/student/{student.id}/transcript"},
            {"label": "📈 Chi tiết điểm", "payload": f"/student/{student.id}"},
            {"label": "📜 Lịch sử vi phạm", "payload": f"/student/{student.id}/violations_timeline"}
        ]
        
        return jsonify({"response": response.strip(), "buttons": buttons})
    
    # Nếu không tìm thấy học sinh
    if class_filter:
        response_text = f"Hiện tại, hệ thống **không tìm thấy** học sinh nào có tên là **{msg}** trong **lớp {class_filter}** 🔍\n\n"
    else:
        response_text = f"Hiện tại, hệ thống **không tìm thấy** học sinh nào có tên là **{msg}** 🔍\n\n"
    
    response_text += "Cô/thầy vui lòng:\n"
    response_text += "• Kiểm tra lại **chính tả** hoặc đầu của họ tên (VD: Hòa hay Hóa).\n"
    response_text += "• Hoặc thử nhập **Mã số học sinh** để tra cứu chính xác hơn!\n\n"
    response_text += "Em luôn sẵn sàng hỗ trợ cô/thầy tiếp tục a. 😊"
    
    # Save AI response
    save_message(session_id, teacher_id, "assistant", response_text)
    
    return jsonify({"response": response_text})

@app.route("/api/chatbot/clear", methods=["POST"])
@login_required
def clear_chat_session():
    """Tạo session mới và xóa session cũ khỏi Flask session"""
    session.pop('chat_session_id', None)
    return jsonify({"status": "success", "message": "Chat đã được làm mới"})


@app.route("/profile")
@login_required
def profile(): return render_template("profile.html", user=current_user)

@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
@admin_required
def edit_profile():
    if request.method == "POST":
        return redirect(url_for("profile"))
    return render_template("edit_profile.html", user=current_user)

#route kho lưu trữ (remake)

# --- TÌM HÀM history() VÀ THAY THẾ BẰNG ĐOẠN NÀY ---

@app.route("/history")
@login_required
def history():
    # 1. Lấy danh sách tuần có dữ liệu
    weeks = [w[0] for w in db.session.query(Violation.week_number).distinct().order_by(Violation.week_number.desc()).all()]
    
    selected_week = request.args.get('week', type=int)
    selected_class = request.args.get('class_select', '').strip()

    # Mặc định chọn tuần mới nhất
    if not selected_week and weeks: selected_week = weeks[0]
        
    violations = []     
    class_rankings = [] 
    pie_data = [0, 0, 0] 
    bar_labels = []      
    bar_data = []        

    if selected_week:
        # A. LẤY CHI TIẾT VI PHẠM (để hiện bảng danh sách lỗi)
        query = db.session.query(Violation).join(Student).filter(Violation.week_number == selected_week)
        if selected_class:
            query = query.filter(Student.student_class == selected_class)
        violations = query.order_by(Violation.date_committed.desc()).all()

        # B. TÍNH TOÁN BIỂU ĐỒ TRÒN & CỘT
        # Thay vì lấy từ Archive, ta tính toán trực tiếp ("Real-time")
        
        # Lấy danh sách học sinh cần tính
        q_students = Student.query
        if selected_class: q_students = q_students.filter_by(student_class=selected_class)
        students = q_students.all()

        count_tot, count_kha, count_tb = 0, 0, 0

        # Tính điểm cho từng học sinh trong tuần đã chọn
        for s in students:
            # Tổng điểm trừ của học sinh này trong tuần đó
            s_deduct = db.session.query(func.sum(Violation.points_deducted))\
                .filter(Violation.student_id == s.id, Violation.week_number == selected_week)\
                .scalar() or 0
            
            s_score = 100 - s_deduct
            
            if s_score >= 90: count_tot += 1
            elif s_score >= 70: count_kha += 1
            else: count_tb += 1

        pie_data = [count_tot, count_kha, count_tb]

        # Top vi phạm
        vios_chart_q = db.session.query(Violation.violation_type_name, func.count(Violation.id).label("c"))\
            .filter(Violation.week_number == selected_week)
        if selected_class:
            vios_chart_q = vios_chart_q.join(Student).filter(Student.student_class == selected_class)
        top = vios_chart_q.group_by(Violation.violation_type_name).order_by(desc("c")).limit(5).all()
        bar_labels = [t[0] for t in top]
        bar_data = [t[1] for t in top]

        # C. TÍNH BẢNG XẾP HẠNG (QUAN TRỌNG: ĐÃ SỬA LẠI LOGIC)
        # Chỉ tính khi không lọc lớp cụ thể
        if not selected_class:
            all_classes_obj = ClassRoom.query.all()
            for cls in all_classes_obj:
                # 1. Lấy tất cả học sinh của lớp
                students_in_class = Student.query.filter_by(student_class=cls.name).all()
                student_count = len(students_in_class)

                if student_count > 0:
                    # 2. Tính tổng điểm trừ của cả lớp trong tuần này
                    total_deduct_class = db.session.query(func.sum(Violation.points_deducted))\
                        .join(Student)\
                        .filter(Student.student_class == cls.name, Violation.week_number == selected_week)\
                        .scalar() or 0
                    
                    # 3. Tính điểm trung bình chuẩn: (Tổng điểm tất cả HS) / Số lượng HS
                    # Tổng điểm tất cả HS = (100 * Số HS) - Tổng điểm trừ
                    HE_SO_PHAT = 15.0
                    
                    avg_deduct = total_deduct_class / student_count
                    avg_score = 100 - (avg_deduct * HE_SO_PHAT)
                    
                    if avg_score < 0: avg_score = 0
                else:
                    total_deduct_class = 0
                    avg_score = 100 

                class_rankings.append({
                    "name": cls.name,
                    "weekly_deduct": total_deduct_class,
                    "avg_score": round(avg_score, 2)
                })
            
            # Sắp xếp từ cao xuống thấp
            class_rankings.sort(key=lambda x: x['avg_score'], reverse=True)

    all_classes = [c.name for c in ClassRoom.query.order_by(ClassRoom.name).all()]

    return render_template("history.html", 
                           weeks=weeks, 
                           selected_week=selected_week, 
                           selected_class=selected_class,
                           violations=violations, 
                           class_rankings=class_rankings,
                           all_classes=all_classes,
                           pie_data=json.dumps(pie_data),
                           bar_labels=json.dumps(bar_labels),
                           bar_data=json.dumps(bar_data))

# --- THÊM ROUTE MỚI ĐỂ XUẤT EXCEL ---

@app.route("/export_history")
@login_required
def export_history():
    selected_week = request.args.get('week', type=int)
    selected_class = request.args.get('class_select', '').strip()
    
    if not selected_week:
        flash("Vui lòng chọn tuần để xuất báo cáo", "error")
        return redirect(url_for('history'))

    # Truy vấn giống hệt bên trên
    query = db.session.query(Violation).join(Student).filter(Violation.week_number == selected_week)
    if selected_class:
        query = query.filter(Student.student_class == selected_class)
    
    violations = query.order_by(Violation.date_committed.desc()).all()
    
    # Tạo dữ liệu cho Excel
    data = []
    for v in violations:
        data.append({
            "Ngày": v.date_committed.strftime('%d/%m/%Y'),
            "Mã HS": v.student.student_code,
            "Họ Tên": v.student.name,
            "Lớp": v.student.student_class,
            "Lỗi Vi Phạm": v.violation_type_name,
            "Điểm Trừ": v.points_deducted,
            "Tuần": v.week_number
        })
    
    # Xuất file
    if data:
        df = pd.read_json(json.dumps(data))
    else:
        df = pd.DataFrame([{"Thông báo": "Không có dữ liệu vi phạm"}])

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f"Tuan_{selected_week}")
        # Tự động điều chỉnh độ rộng cột (cơ bản)
        worksheet = writer.sheets[f"Tuan_{selected_week}"]
        for idx, col in enumerate(df.columns):
            worksheet.column_dimensions[chr(65 + idx)].width = 20

    output.seek(0)
    filename = f"BaoCao_ViPham_Tuan{selected_week}"
    if selected_class:
        filename += f"_{selected_class}"
    filename += ".xlsx"
    
    return send_file(output, download_name=filename, as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --- Copy đoạn này thay thế cho hàm weekly_report cũ ---

@app.route("/weekly_report")
@login_required
def weekly_report():
    # 1. Lấy tuần hiện tại của hệ thống
    w_cfg = SystemConfig.query.filter_by(key="current_week").first()
    sys_week = int(w_cfg.value) if w_cfg else 1
    
    # 2. Lấy tuần được chọn từ URL (nếu không có thì mặc định là tuần hệ thống)
    selected_week = request.args.get('week', sys_week, type=int)
    
    # 3. Lấy danh sách vi phạm chi tiết để hiện bảng
    vios = db.session.query(Violation, Student).join(Student).filter(Violation.week_number == selected_week).all()
    
    total_errors = len(vios)
    total_points = sum(v.Violation.points_deducted for v in vios)
    
    # 4. Tính toán Bảng xếp hạng (ĐÃ SỬA LOGIC)
    all_classes = ClassRoom.query.all()
    class_data = []
    
    for cls in all_classes:
        # Lấy danh sách học sinh thực tế của lớp
        students_in_class = Student.query.filter_by(student_class=cls.name).all()
        student_count = len(students_in_class)
        
        # Bỏ qua nếu lớp không có học sinh (tránh chia cho 0)
        if student_count == 0:
            continue
        
        # Tính tổng điểm trừ của cả lớp trong tuần đó
        weekly_deduct = db.session.query(func.sum(Violation.points_deducted))\
            .join(Student)\
            .filter(Student.student_class == cls.name, Violation.week_number == selected_week)\
            .scalar() or 0
        
        # --- CÔNG THỨC CHUẨN: (Tổng điểm có sẵn - Tổng trừ) / Số lượng HS ---
        HE_SO_PHAT = 15.0 
        
        # Công thức: 100 - (Điểm trừ trung bình * Hệ số)
        avg_deduct = weekly_deduct / student_count
        avg_score = 100 - (avg_deduct * HE_SO_PHAT)
        
        # Đảm bảo không bị âm điểm
        if avg_score < 0: avg_score = 0
        
        class_data.append({
            'name': cls.name,
            'avg_score': round(avg_score, 2),
            'weekly_deduct': weekly_deduct
        })
    
    # Sắp xếp từ cao xuống thấp
    class_rankings = sorted(class_data, key=lambda x: x['avg_score'], reverse=True)
    
    return render_template("weekly_report.html", 
                           violations=vios, 
                           selected_week=selected_week, 
                           system_week=sys_week, 
                           total_points=total_points, 
                           total_errors=total_errors, 
                           class_rankings=class_rankings)

@app.route("/export_report")
@login_required
def export_report():
    week = request.args.get('week', type=int)
    if not week: return "Vui lòng chọn tuần", 400
    violations = db.session.query(Violation, Student).join(Student).filter(Violation.week_number == week).all()
    data = [{"Tên": r.Student.name, "Lớp": r.Student.student_class, "Lỗi": r.Violation.violation_type_name} for r in violations]
    df = pd.read_json(json.dumps(data)) if data else pd.DataFrame([{"Thông báo": "Trống"}])
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name=f"Report_{week}.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --- Thay thế hàm student_detail cũ ---
@app.route("/student/<int:student_id>")
@login_required
def student_detail(student_id):
    # Kiểm tra quyền truy cập học sinh
    if not can_access_student(student_id):
        flash("Bạn không có quyền xem học sinh này!", "error")
        return redirect(url_for('dashboard'))
    
    student = db.session.get(Student, student_id)
    if not student:
        flash("Học sinh không tồn tại.", "error")
        return redirect(url_for('manage_students'))

    # 1. Lấy danh sách các tuần có dữ liệu (từ cả violations và bonuses)
    violation_weeks = [w[0] for w in db.session.query(Violation.week_number).distinct().all()]
    bonus_weeks = [w[0] for w in db.session.query(BonusRecord.week_number).distinct().all()]
    weeks = sorted(set(violation_weeks + bonus_weeks), reverse=True)
    
    # 2. Xác định tuần được chọn (Mặc định là tuần hiện tại của hệ thống)
    w_cfg = SystemConfig.query.filter_by(key="current_week").first()
    sys_current_week = int(w_cfg.value) if w_cfg else 1
    
    selected_week = request.args.get('week', type=int)
    if not selected_week:
        selected_week = sys_current_week

    # 3. Lấy vi phạm CHỈ CỦA TUẦN ĐÓ
    violations = Violation.query.filter_by(student_id=student_id, week_number=selected_week)\
        .order_by(Violation.date_committed.asc()).all()

    # 4. Lấy điểm cộng CHỈ CỦA TUẦN ĐÓ
    bonuses = BonusRecord.query.filter_by(student_id=student_id, week_number=selected_week)\
        .order_by(BonusRecord.date_awarded.asc()).all()

    # 5. Tính toán dữ liệu biểu đồ (Reset về 100 mỗi đầu tuần)
    chart_labels = ["Đầu tuần"]
    chart_scores = [100]
    
    # Kết hợp violations và bonuses theo thời gian
    events = []
    for v in violations:
        events.append({'type': 'violation', 'date': v.date_committed, 'points': -v.points_deducted, 'name': v.violation_type_name})
    for b in bonuses:
        events.append({'type': 'bonus', 'date': b.date_awarded, 'points': b.points_added, 'name': b.bonus_type_name})
    
    # Sắp xếp theo thời gian
    events.sort(key=lambda x: x['date'])
    
    current_score = 100
    for event in events:
        current_score += event['points']  # -points cho violation, +points cho bonus
        date_str = event['date'].strftime('%d/%m')
        chart_labels.append(date_str)
        chart_scores.append(current_score)
    
    # Tính tổng
    total_deducted = sum(v.points_deducted for v in violations)
    total_added = sum(b.points_added for b in bonuses)
    
    # Điểm hiển thị trên thẻ (Score Card)
    display_score = 100 - total_deducted + total_added

    # Cảnh báo nếu điểm thấp
    warning = None
    if display_score < 70:
        warning = f"Học sinh này đang có điểm nề nếp thấp ({display_score} điểm) trong tuần {selected_week}. Cần nhắc nhở!"

    return render_template("student_detail.html", 
                           student=student,
                           weeks=weeks,
                           selected_week=selected_week,
                           violations=violations,
                           bonuses=bonuses,
                           chart_labels=json.dumps(chart_labels),
                           chart_scores=json.dumps(chart_scores),
                           display_score=display_score,
                           total_added=total_added,
                           warning=warning)


# --- Thay thế hàm api generate_report cũ (Cập nhật cho Ollama & Context Tuần) ---
@app.route("/api/generate_report/<int:student_id>", methods=["POST"])
@login_required
def generate_report(student_id):
    try:
        data = request.get_json() or {}
        week = data.get('week') # Nhận tham số tuần từ Frontend
        
        student = db.session.get(Student, student_id)
        if not student:
            return jsonify({"error": "Học sinh không tồn tại"}), 404

        # Lấy dữ liệu vi phạm của tuần được chọn
        query = Violation.query.filter_by(student_id=student_id)
        if week:
            query = query.filter_by(week_number=week)
            time_context = f"TUẦN {week}"
        else:
            time_context = "TỪ TRƯỚC ĐẾN NAY"
            
        violations = query.all()
        
        # Tổng hợp dữ liệu gửi cho AI
        total_deducted = sum(v.points_deducted for v in violations)
        final_score = 100 - total_deducted
        
        violation_list = [f"- {v.violation_type_name} (ngày {v.date_committed.strftime('%d/%m')})" for v in violations]
        violation_text = "\n".join(violation_list) if violation_list else "Không có vi phạm nào."

        # Prompt dành cho Ollama
        prompt = f"""
        Đóng vai Trợ lý Giáo viên Chủ nhiệm. Hãy viết một nhận xét ngắn (khoảng 3-4 câu) gửi cho phụ huynh về tình hình nề nếp của học sinh:
        - Tên: {student.name}
        - Thời gian: {time_context}
        - Điểm nề nếp: {final_score}/100
        - Các lỗi vi phạm:
        {violation_text}

        Yêu cầu:
        1. Giọng văn lịch sự, xây dựng, quan tâm.
        2. Nếu điểm cao (>=90): Khen ngợi và động viên phát huy.
        3. Nếu điểm thấp (<70): Nhắc nhở khéo léo và đề nghị gia đình phối hợp.
        4. Trả lời bằng Tiếng Việt. Không cần chào hỏi rườm rà, vào thẳng nội dung nhận xét.
        """

        # Gọi Ollama (Chạy model Text: ollama run gemini-3-flash-preview)
        model_name = os.environ.get("OLLAMA_TEXT_MODEL", OLLAMA_MODEL) 
        
        response = ollama.chat(model=model_name, messages=[
            {'role': 'user', 'content': prompt},
        ])
        
        ai_reply = response['message']['content']
        return jsonify({"report": ai_reply})

    except Exception as e:
        print(f"AI Error: {str(e)}")
        return jsonify({"error": "Lỗi khi gọi trợ lý ảo. Vui lòng thử lại sau."}), 500

@app.route("/manage_subjects", methods=["GET", "POST"])
@login_required
def manage_subjects():
    """Quản lý danh sách môn học"""
    if request.method == "POST":
        name = request.form.get("subject_name", "").strip()
        code = request.form.get("subject_code", "").strip().upper()
        description = request.form.get("description", "").strip()
        num_tx = int(request.form.get("num_tx_columns", 3))
        num_gk = int(request.form.get("num_gk_columns", 1))
        num_hk = int(request.form.get("num_hk_columns", 1))
        
        if not name or not code:
            flash("Vui lòng nhập tên và mã môn học!", "error")
            return redirect(url_for("manage_subjects"))
        
        if Subject.query.filter_by(code=code).first():
            flash("Mã môn học đã tồn tại!", "error")
            return redirect(url_for("manage_subjects"))
        
        subject = Subject(
            name=name, 
            code=code, 
            description=description,
            num_tx_columns=num_tx,
            num_gk_columns=num_gk,
            num_hk_columns=num_hk
        )
        db.session.add(subject)
        db.session.commit()
        flash(f"Đã thêm môn {name}", "success")
        return redirect(url_for("manage_subjects"))
    
    subjects = Subject.query.order_by(Subject.name).all()
    return render_template("manage_subjects.html", subjects=subjects)

@app.route("/edit_subject/<int:subject_id>", methods=["GET", "POST"])
@login_required
def edit_subject(subject_id):
    """Sửa thông tin môn học"""
    subject = db.session.get(Subject, subject_id)
    if not subject:
        flash("Không tìm thấy môn học!", "error")
        return redirect(url_for("manage_subjects"))
    
    if request.method == "POST":
        subject.name = request.form.get("subject_name", "").strip()
        subject.code = request.form.get("subject_code", "").strip().upper()
        subject.description = request.form.get("description", "").strip()
        subject.num_tx_columns = int(request.form.get("num_tx_columns", 3))
        subject.num_gk_columns = int(request.form.get("num_gk_columns", 1))
        subject.num_hk_columns = int(request.form.get("num_hk_columns", 1))
        
        db.session.commit()
        flash("Đã cập nhật môn học!", "success")
        return redirect(url_for("manage_subjects"))
    
    return render_template("edit_subject.html", subject=subject)

@app.route("/delete_subject/<int:subject_id>", methods=["POST"])
@login_required
def delete_subject(subject_id):
    """Xóa môn học"""
    subject = db.session.get(Subject, subject_id)
    if subject:
        db.session.delete(subject)
        db.session.commit()
        flash("Đã xóa môn học!", "success")
    return redirect(url_for("manage_subjects"))

@app.route("/manage_grades")
@login_required
def manage_grades():
    """Danh sách học sinh để chọn nhập điểm"""
    search = request.args.get('search', '').strip()
    selected_class = request.args.get('class_select', '').strip()
    
    q = get_accessible_students()  # Filter by role
    if selected_class:
        q = q.filter_by(student_class=selected_class)
    if search:
        q = q.filter(or_(
            Student.name.ilike(f"%{search}%"),
            Student.student_code.ilike(f"%{search}%")
        ))
    
    students = q.order_by(Student.student_code.asc()).all()
    return render_template("manage_grades.html", students=students, search_query=search, selected_class=selected_class)

@app.route("/student_grades/<int:student_id>", methods=["GET", "POST"])
@login_required
def student_grades(student_id):
    """Xem và nhập điểm cho học sinh"""
    # Kiểm tra quyền truy cập học sinh
    if not can_access_student(student_id):
        flash("Bạn không có quyền xem học sinh này!", "error")
        return redirect(url_for('dashboard'))
    
    student = db.session.get(Student, student_id)
    if not student:
        flash("Không tìm thấy học sinh!", "error")
        return redirect(url_for("manage_grades"))
    
    if request.method == "POST":
        subject_id = request.form.get("subject_id")
        grade_type = request.form.get("grade_type")
        column_index = int(request.form.get("column_index", 1))
        score = request.form.get("score")
        semester = int(request.form.get("semester", 1))
        school_year = request.form.get("school_year", "2023-2024")
        
        if not all([subject_id, grade_type, score]):
            flash("Vui lòng điền đầy đủ thông tin!", "error")
            return redirect(url_for("student_grades", student_id=student_id))
        
        # Kiểm tra quyền sửa môn học
        if not can_access_subject(int(subject_id)):
            flash("Bạn không có quyền sửa điểm môn này!", "error")
            return redirect(url_for("student_grades", student_id=student_id))
        
        try:
            score_float = float(score)
            if score_float < 0 or score_float > 10:
                flash("Điểm phải từ 0 đến 10!", "error")
                return redirect(url_for("student_grades", student_id=student_id))
        except ValueError:
            flash("Điểm không hợp lệ!", "error")
            return redirect(url_for("student_grades", student_id=student_id))
        
        existing = Grade.query.filter_by(
            student_id=student_id,
            subject_id=subject_id,
            grade_type=grade_type,
            column_index=column_index,
            semester=semester,
            school_year=school_year
        ).first()
        
        subject_obj = db.session.get(Subject, int(subject_id))
        subject_name = subject_obj.name if subject_obj else 'N/A'
        
        if existing:
            old_score_val = existing.score
            existing.score = score_float
            log_change('grade_update', f'Cập nhật điểm {grade_type} môn {subject_name}: {old_score_val} → {score_float}', student_id=student_id, student_name=student.name, student_class=student.student_class, old_value=old_score_val, new_value=score_float)
            flash("Đã cập nhật điểm!", "success")
        else:
            grade = Grade(
                student_id=student_id,
                subject_id=subject_id,
                grade_type=grade_type,
                column_index=column_index,
                score=score_float,
                semester=semester,
                school_year=school_year
            )
            db.session.add(grade)
            log_change('grade', f'Thêm điểm {grade_type} môn {subject_name}: {score_float}', student_id=student_id, student_name=student.name, student_class=student.student_class, new_value=score_float)
            flash("Đã thêm điểm!", "success")
        
        db.session.commit()
        
        # Thông báo cho GVCN lớp
        try:
            if student.student_class:
                subject = db.session.get(Subject, int(subject_id))
                create_notification(
                    title=f"📊 Điểm mới - {student.name}",
                    message=f"{current_user.full_name} đã nhập điểm {subject.name if subject else 'môn học'} cho {student.name} (Lớp {student.student_class})",
                    notification_type='grade',
                    target_role=student.student_class
                )
        except:
            pass  # Không để lỗi notification làm gián đoạn
        
        return redirect(url_for("student_grades", student_id=student_id))
    
    subjects = Subject.query.order_by(Subject.name).all()
    semester = int(request.args.get('semester', 1))
    school_year = request.args.get('school_year', '2023-2024')
    
    grades = Grade.query.filter_by(
        student_id=student_id,
        semester=semester,
        school_year=school_year
    ).all()
    
    grades_by_subject = {}
    for subject in subjects:
        subject_grades = {
            'TX': {},
            'GK': {},
            'HK': {}
        }
        for grade in grades:
            if grade.subject_id == subject.id:
                subject_grades[grade.grade_type][grade.column_index] = grade
        grades_by_subject[subject.id] = subject_grades
    
    # Truyền assigned_subject_id để disable input field trong template
    assigned_subject_id = current_user.assigned_subject_id if current_user.role == 'subject_teacher' else None
    
    return render_template(
        "student_grades.html",
        student=student,
        subjects=subjects,
        grades_by_subject=grades_by_subject,
        semester=semester,
        school_year=school_year,
        assigned_subject_id=assigned_subject_id
    )

@app.route("/delete_grade/<int:grade_id>", methods=["POST"])
@login_required
def delete_grade(grade_id):
    """Xóa một điểm"""
    grade = db.session.get(Grade, grade_id)
    if grade:
        student_id = grade.student_id
        student = db.session.get(Student, student_id)
        subject = db.session.get(Subject, grade.subject_id)
        log_change('grade_delete', f'Xóa điểm {grade.grade_type} môn {subject.name if subject else "N/A"}: {grade.score}', student_id=student_id, student_name=student.name if student else None, student_class=student.student_class if student else None, old_value=grade.score)
        db.session.delete(grade)
        db.session.commit()
        flash("Đã xóa điểm!", "success")
        return redirect(url_for("student_grades", student_id=student_id))
    return redirect(url_for("manage_grades"))

@app.route("/api/update_grade/<int:grade_id>", methods=["POST"])
@login_required
def update_grade_api(grade_id):
    """API endpoint để cập nhật điểm inline"""
    try:
        data = request.get_json()
        new_score = float(data.get("score", 0))
        
        if new_score < 0 or new_score > 10:
            return jsonify({"success": False, "error": "Điểm phải từ 0 đến 10"}), 400
        
        grade = db.session.get(Grade, grade_id)
        if not grade:
            return jsonify({"success": False, "error": "Không tìm thấy điểm"}), 404
        
        old_score_val = grade.score
        grade.score = new_score
        student = db.session.get(Student, grade.student_id)
        subject = db.session.get(Subject, grade.subject_id)
        log_change('grade_update', f'Cập nhật điểm inline {grade.grade_type} môn {subject.name if subject else "N/A"}: {old_score_val} → {new_score}', student_id=grade.student_id, student_name=student.name if student else None, student_class=student.student_class if student else None, old_value=old_score_val, new_value=new_score)
        db.session.commit()
        
        return jsonify({"success": True, "score": new_score})
    except ValueError:
        return jsonify({"success": False, "error": "Điểm không hợp lệ"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/student/<int:student_id>/transcript")
@login_required
def student_transcript(student_id):
    """Xem bảng điểm tổng hợp (học bạ) của học sinh"""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Không tìm thấy học sinh!", "error")
        return redirect(url_for("manage_grades"))
    
    semester = int(request.args.get('semester', 1))
    school_year = request.args.get('school_year', '2023-2024')
    
    subjects = Subject.query.order_by(Subject.name).all()
    
    transcript_data = []
    for subject in subjects:
        grades = Grade.query.filter_by(
            student_id=student_id,
            subject_id=subject.id,
            semester=semester,
            school_year=school_year
        ).all()
        
        tx_scores = [g.score for g in grades if g.grade_type == 'TX']
        gk_scores = [g.score for g in grades if g.grade_type == 'GK']
        hk_scores = [g.score for g in grades if g.grade_type == 'HK']
        
        avg_score = None
        if tx_scores and gk_scores and hk_scores:
            avg_tx = sum(tx_scores) / len(tx_scores)
            avg_gk = sum(gk_scores) / len(gk_scores)
            avg_hk = sum(hk_scores) / len(hk_scores)
            avg_score = round((avg_tx + avg_gk * 2 + avg_hk * 3) / 6, 2)
        
        transcript_data.append({
            'subject': subject,
            'tx_scores': tx_scores,
            'gk_scores': gk_scores,
            'hk_scores': hk_scores,
            'avg_score': avg_score
        })
    
    valid_averages = [item['avg_score'] for item in transcript_data if item['avg_score'] is not None]
    gpa = round(sum(valid_averages) / len(valid_averages), 2) if valid_averages else None
    
    return render_template(
        "student_transcript.html",
        student=student,
        transcript_data=transcript_data,
        semester=semester,
        school_year=school_year,
        gpa=gpa
    )


@app.route("/student/<int:student_id>/violations_timeline")
@login_required
def violations_timeline(student_id):
    """Timeline lịch sử vi phạm của học sinh"""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Không tìm thấy học sinh!", "error")
        return redirect(url_for("manage_students"))
    
    violations = Violation.query.filter_by(student_id=student_id)\
        .order_by(Violation.date_committed.desc()).all()
    
    violations_by_week = db.session.query(
        Violation.week_number,
        func.count(Violation.id).label('count'),
        func.sum(Violation.points_deducted).label('total_deducted')
    ).filter(Violation.student_id == student_id)\
    .group_by(Violation.week_number)\
    .order_by(Violation.week_number).all()
    
    violations_by_type = db.session.query(
        Violation.violation_type_name,
        func.count(Violation.id).label('count')
    ).filter(Violation.student_id == student_id)\
    .group_by(Violation.violation_type_name)\
    .order_by(desc('count')).all()
    
    week_labels = [w[0] for w in violations_by_week]
    week_counts = [w[1] for w in violations_by_week]
    type_labels = [t[0] for t in violations_by_type]
    type_counts = [t[1] for t in violations_by_type]
    
    return render_template(
        "violations_timeline.html",
        student=student,
        violations=violations,
        violations_by_week=violations_by_week,
        violations_by_type=violations_by_type,
        week_labels=week_labels,
        week_counts=week_counts,
        type_labels=type_labels,
        type_counts=type_counts
    )

@app.route("/student/<int:student_id>/parent_report")
@login_required
def parent_report(student_id):
    """Báo cáo tổng hợp cho phụ huynh"""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Không tìm thấy học sinh!", "error")
        return redirect(url_for("manage_students"))
    
    semester = int(request.args.get('semester', 1))
    school_year = request.args.get('school_year', '2023-2024')
    
    subjects = Subject.query.order_by(Subject.name).all()
    transcript_data = []
    for subject in subjects:
        grades = Grade.query.filter_by(
            student_id=student_id,
            subject_id=subject.id,
            semester=semester,
            school_year=school_year
        ).all()
        
        tx_scores = [g.score for g in grades if g.grade_type == 'TX']
        gk_scores = [g.score for g in grades if g.grade_type == 'GK']
        hk_scores = [g.score for g in grades if g.grade_type == 'HK']
        
        avg_score = None
        if tx_scores and gk_scores and hk_scores:
            avg_tx = sum(tx_scores) / len(tx_scores)
            avg_gk = sum(gk_scores) / len(gk_scores)
            avg_hk = sum(hk_scores) / len(hk_scores)
            avg_score = round((avg_tx + avg_gk * 2 + avg_hk * 3) / 6, 2)
        
        transcript_data.append({
            'subject': subject,
            'tx_scores': tx_scores,
            'gk_scores': gk_scores,
            'hk_scores': hk_scores,
            'avg_score': avg_score
        })
    
    valid_averages = [item['avg_score'] for item in transcript_data if item['avg_score'] is not None]
    gpa = round(sum(valid_averages) / len(valid_averages), 2) if valid_averages else None
    
    current_week_cfg = SystemConfig.query.filter_by(key="current_week").first()
    current_week = int(current_week_cfg.value) if current_week_cfg else 1
    
    recent_violations = Violation.query.filter_by(student_id=student_id)\
        .filter(Violation.week_number >= max(1, current_week - 4))\
        .order_by(Violation.date_committed.desc())\
        .limit(10).all()
    
    total_violations = Violation.query.filter_by(student_id=student_id).count()
    
    return render_template(
        "parent_report.html",
        student=student,
        transcript_data=transcript_data,
        gpa=gpa,
        semester=semester,
        school_year=school_year,
        recent_violations=recent_violations,
        total_violations=total_violations,
        current_week=current_week,
        now=datetime.datetime.now()
    )

@app.route("/api/generate_parent_report/<int:student_id>", methods=["POST"])
@login_required
def generate_parent_report(student_id):
    """Gọi AI tạo nhận xét tổng hợp cho phụ huynh"""
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({"error": "Không tìm thấy học sinh"}), 404
    
    semester = int(request.json.get('semester', 1))
    school_year = request.json.get('school_year', '2023-2024')
    
    subjects = Subject.query.all()
    grades_info = []
    for subject in subjects:
        grades = Grade.query.filter_by(
            student_id=student_id,
            subject_id=subject.id,
            semester=semester,
            school_year=school_year
        ).all()
        
        tx_scores = [g.score for g in grades if g.grade_type == 'TX']
        gk_scores = [g.score for g in grades if g.grade_type == 'GK']
        hk_scores = [g.score for g in grades if g.grade_type == 'HK']
        
        if tx_scores and gk_scores and hk_scores:
            avg_tx = sum(tx_scores) / len(tx_scores)
            avg_gk = sum(gk_scores) / len(gk_scores)
            avg_hk = sum(hk_scores) / len(hk_scores)
            avg_score = round((avg_tx + avg_gk * 2 + avg_hk * 3) / 6, 2)
            grades_info.append(f"{subject.name}: {avg_score}")
    
    valid_avg = [float(g.split(': ')[1]) for g in grades_info if g]
    gpa = round(sum(valid_avg) / len(valid_avg), 2) if valid_avg else 0
    
    violations = Violation.query.filter_by(student_id=student_id)\
        .order_by(Violation.date_committed.desc())\
        .limit(10).all()
    
    violation_summary = f"{len(violations)} vi phạm gần đây" if violations else "Không có vi phạm"
    
    prompt = f"""Bạn là giáo viên chủ nhiệm. Hãy viết nhận xét NGẮN GỌN (3-4 câu) gửi phụ huynh về học sinh {student.name} (Lớp {student.student_class}):

THÔNG TIN HỌC TẬP:
- GPA học kỳ {semester}: {gpa}/10
- Điểm các môn: {', '.join(grades_info) if grades_info else 'Chưa có điểm'}

THÔNG TIN RÈN LUYỆN:
- Điểm rèn luyện hiện tại: {student.current_score}/100
- {violation_summary}

Hãy viết nhận xét xúc tích, chân thành, khích lệ học sinh và đưa ra lời khuyên cụ thể. Không cần xưng hô, viết trực tiếp nội dung."""
    
    response, error = _call_gemini(prompt)
    
    if error:
        return jsonify({"error": error}), 500
    
    return jsonify({"report": response})


@app.route("/admin/reset_week", methods=["POST"])
@login_required
def reset_week():
    try:
        # 1. Lấy tuần hiển thị hiện tại
        week_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week_num = int(week_cfg.value) if week_cfg else 1
        
        # 2. Lưu trữ dữ liệu tuần cũ
        save_weekly_archive(current_week_num)
        
        # 3. Reset điểm toàn bộ học sinh về 100
        db.session.query(Student).update({Student.current_score: 100})
        
        # 4. Tăng số tuần hiển thị lên 1
        if week_cfg:
            week_cfg.value = str(current_week_num + 1)
            
        # 5. Cập nhật "Dấu vết" tuần ISO để tắt cảnh báo
        current_iso = get_current_iso_week()
        last_reset_cfg = SystemConfig.query.filter_by(key="last_reset_week_id").first()
        if not last_reset_cfg:
            db.session.add(SystemConfig(key="last_reset_week_id", value=current_iso))
        else:
            last_reset_cfg.value = current_iso
            
        db.session.commit()
        flash(f"Đã kết thúc Tuần {current_week_num}. Hệ thống chuyển sang Tuần {current_week_num + 1}.", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi: {str(e)}", "error")
        
    return redirect(url_for("dashboard"))
@app.route("/admin/update_week", methods=["POST"])
def update_week():
    c = SystemConfig.query.filter_by(key="current_week").first()
    if c: c.value = str(request.form["new_week"]); db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/changelog")
@login_required
def changelog():
    """Xem lịch sử thay đổi CSDL - Tất cả người dùng đều có thể xem"""
    page = request.args.get('page', 1, type=int)
    per_page = 30
    search = request.args.get('search', '').strip()
    change_type_filter = request.args.get('type', '').strip()
    
    q = ChangeLog.query
    
    if search:
        q = q.filter(
            db.or_(
                ChangeLog.description.ilike(f'%{search}%'),
                ChangeLog.student_name.ilike(f'%{search}%'),
                ChangeLog.student_class.ilike(f'%{search}%')
            )
        )
    
    if change_type_filter:
        q = q.filter(ChangeLog.change_type == change_type_filter)
    
    # Sắp xếp mới nhất trước
    logs = q.order_by(ChangeLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # Lấy danh sách change_type duy nhất để filter
    all_types = db.session.query(ChangeLog.change_type).distinct().all()
    type_labels = {
        'violation': 'Vi phạm',
        'bonus': 'Điểm cộng',
        'grade': 'Thêm điểm',
        'grade_update': 'Cập nhật điểm',
        'grade_delete': 'Xóa điểm',
        'violation_delete': 'Xóa vi phạm',
        'score_reset': 'Reset điểm',
        'bulk_violation': 'Nhập VP hàng loạt'
    }
    
    return render_template("changelog.html", 
        logs=logs, 
        search=search, 
        change_type_filter=change_type_filter,
        all_types=[t[0] for t in all_types],
        type_labels=type_labels
    )

@app.route("/api/check_duplicate_student", methods=["POST"])
def check_duplicate_student(): return jsonify([])

def create_database():
    db.create_all()
    if not Teacher.query.first(): 
        db.session.add(Teacher(username="admin", password="admin", full_name="Admin", role="admin"))
    if not SystemConfig.query.first(): db.session.add(SystemConfig(key="current_week", value="1"))
    if not ViolationType.query.first(): db.session.add(ViolationType(name="Đi muộn", points_deducted=2))
    db.session.commit()

if __name__ == "__main__":
    with app.app_context(): create_database()

@app.route("/delete_violation/<int:violation_id>", methods=["POST"])
@login_required
def delete_violation(violation_id):
    try:
        # 1. Tìm bản ghi vi phạm
        violation = Violation.query.get_or_404(violation_id)
        student = Student.query.get(violation.student_id)
        
        # 2. KHÔI PHỤC ĐIỂM SỐ
        # Cộng trả lại điểm đã trừ
        if student:
            old_score = student.current_score
            student.current_score += violation.points_deducted
            # Đảm bảo điểm không vượt quá 100 (nếu quy chế là max 100)
            if student.current_score > 100:
                student.current_score = 100
            log_change('violation_delete', f'Xóa vi phạm: {violation.violation_type_name} (hoàn +{violation.points_deducted} điểm)', student_id=student.id, student_name=student.name, student_class=student.student_class, old_value=old_score, new_value=student.current_score)
        
        # 3. Xóa vi phạm
        db.session.delete(violation)
        db.session.commit()
        
        flash(f"Đã xóa vi phạm và khôi phục {violation.points_deducted} điểm cho học sinh.", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi khi xóa: {str(e)}", "error")
        
    # Quay lại trang Timeline của học sinh đó
    return redirect(url_for('violations_timeline', student_id=student.id if student else 0))

import unidecode # Thư viện xử lý tiếng Việt không dấu
import re

@app.route("/import_students", methods=["GET", "POST"])
@login_required
def import_students():
    """Import students from Excel with columns: Mã học sinh, Họ và tên, Lớp"""
    if request.method == "POST":
        file = request.files.get("file")
        
        if not file:
            flash("Vui lòng chọn file Excel!", "error")
            return redirect(request.url)

        try:
            # Save temporary file
            if not os.path.exists("uploads"):
                os.makedirs("uploads")
            
            filename = f"import_students_{uuid.uuid4().hex[:8]}.xlsx"
            filepath = os.path.join("uploads", filename)
            file.save(filepath)

            # Đọc file Excel
            df = pd.read_excel(filepath)
            # Chuẩn hóa tên cột về chữ thường để dễ tìm
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            preview_data = []
            
            # Tìm các cột cần thiết
            code_col = next((c for c in df.columns if "mã" in c or "code" in c), None)
            name_col = next((c for c in df.columns if "tên" in c or "name" in c), None)
            class_col = next((c for c in df.columns if "lớp" in c or "class" in c), None)
            
            if not code_col or not name_col or not class_col:
                if os.path.exists(filepath): os.remove(filepath)
                flash("File Excel cần có 3 cột: 'Mã học sinh', 'Họ và tên', 'Lớp'", "error")
                return redirect(request.url)

            # Lặp qua từng dòng trong Excel
            for index, row in df.iterrows():
                student_code = str(row[code_col]).strip()
                name = str(row[name_col]).strip()
                s_class = str(row[class_col]).strip()
                
                # Bỏ qua dòng trống
                if not name or name.lower() == 'nan': 
                    continue
                if not student_code or student_code.lower() == 'nan':
                    continue
                
                preview_data.append({
                    "name": name,
                    "class": s_class,
                    "student_code": student_code
                })
            
            # Chuyển sang trang xác nhận
            return render_template("confirm_import.html", students=preview_data, file_path=filepath)

        except Exception as e:
            flash(f"Lỗi đọc file: {str(e)}", "error")
            return redirect(request.url)

    return render_template("import_students.html")


@app.route("/download_student_template")
@login_required
def download_student_template():
    """Download Excel template for student import"""
    sample_data = {
        'Mã học sinh': ['36 ANHA - 001001', '36 ANHA - 001002', '36 TINA - 001001'],
        'Họ và tên': ['Nguyễn Văn A', 'Trần Thị B', 'Lê Hoàng C'],
        'Lớp': ['10 Anh A', '10 Anh A', '10 Tin A']
    }
    df = pd.DataFrame(sample_data)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Danh sách học sinh')
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='mau_nhap_hoc_sinh.xlsx'
    )




@app.route("/save_imported_students", methods=["POST"])
@login_required
def save_imported_students():
    """Bước 2: Lưu vào CSDL sau khi xác nhận"""
    filepath = request.form.get("file_path")
    if not filepath or not os.path.exists(filepath):
        flash("File nhập liệu không tồn tại hoặc đã hết hạn. Vui lòng thử lại.", "error")
        return redirect(url_for('import_students'))
        
    try:
        df = pd.read_excel(filepath)
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        code_col = next((c for c in df.columns if "mã" in c or "code" in c), None)
        name_col = next((c for c in df.columns if "tên" in c or "name" in c), None)
        class_col = next((c for c in df.columns if "lớp" in c or "class" in c), None)
        
        count = 0
        skipped = 0
        for index, row in df.iterrows():
            student_code = str(row[code_col]).strip()
            name = str(row[name_col]).strip()
            s_class = str(row[class_col]).strip()
            
            if not name or name.lower() == 'nan': continue
            if not student_code or student_code.lower() == 'nan': continue
            
            # 1. Kiểm tra trùng mã trong DB
            if Student.query.filter_by(student_code=student_code).first():
                skipped += 1
                continue 
            
            # 2. Tự động tạo Lớp mới nếu chưa có
            if not ClassRoom.query.filter_by(name=s_class).first():
                db.session.add(ClassRoom(name=s_class))
            
            # 3. Thêm học sinh
            new_student = Student(name=name, student_class=s_class, student_code=student_code)
            db.session.add(new_student)
            
            count += 1
            
        db.session.commit()
        
        # Cleanup
        if os.path.exists(filepath):
            os.remove(filepath)
            
        flash(f"Kết quả nhập liệu: Thêm mới {count} học sinh. Bỏ qua {skipped} học sinh (đã tồn tại).", "success" if count > 0 else "warning")
        return redirect(url_for('manage_students'))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi khi lưu: {str(e)}", "error")
        return redirect(url_for('import_students'))
# --- DÁN ĐOẠN NÀY XUỐNG CUỐI FILE app.py ---

@app.route("/admin/fix_scores")
@login_required
def fix_scores():
    """Hàm này giúp tính lại điểm cho toàn bộ học sinh dựa trên lỗi vi phạm"""
    try:
        # 1. Lấy danh sách tất cả học sinh
        students = Student.query.all()
        count = 0
        
        for s in students:
            # 2. Tìm tất cả lỗi vi phạm của học sinh này trong DB
            violations = Violation.query.filter_by(student_id=s.id).all()
            
            # 3. Cộng tổng điểm phạt
            total_deducted = sum(v.points_deducted for v in violations)
            
            # 4. Reset điểm về 100 rồi trừ đi tổng lỗi
            s.current_score = 100 - total_deducted
            
            count += 1
            
        # 5. Lưu tất cả thay đổi vào Database
        db.session.commit()
        
        flash(f"Đã sửa điểm thành công cho {count} học sinh!", "success")
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        return f"Có lỗi xảy ra: {str(e)}"   


# === BONUS POINTS ROUTES ===

@app.route("/manage_bonus_types", methods=["GET", "POST"])
@login_required
def manage_bonus_types():
    """Quản lý loại điểm cộng"""
    if request.method == "POST":
        name = request.form.get("bonus_name", "").strip()
        points = int(request.form.get("points", 0))
        description = request.form.get("description", "").strip()
        
        if name and points > 0:
            if not BonusType.query.filter_by(name=name).first():
                db.session.add(BonusType(name=name, points_added=points, description=description or None))
                db.session.commit()
                flash("Đã thêm loại điểm cộng mới!", "success")
            else:
                flash("Loại điểm cộng này đã tồn tại!", "error")
        else:
            flash("Vui lòng nhập đầy đủ thông tin!", "error")
        return redirect(url_for("manage_bonus_types"))
    
    bonus_types = BonusType.query.order_by(BonusType.points_added.desc()).all()
    return render_template("manage_bonus_types.html", bonus_types=bonus_types)


@app.route("/edit_bonus_type/<int:bonus_id>", methods=["GET", "POST"])
@login_required
def edit_bonus_type(bonus_id):
    """Sửa loại điểm cộng"""
    bonus = db.session.get(BonusType, bonus_id)
    if not bonus:
        flash("Không tìm thấy loại điểm cộng!", "error")
        return redirect(url_for("manage_bonus_types"))
    
    if request.method == "POST":
        bonus.name = request.form.get("bonus_name", "").strip()
        bonus.points_added = int(request.form.get("points", 0))
        bonus.description = request.form.get("description", "").strip() or None
        db.session.commit()
        flash("Đã cập nhật loại điểm cộng!", "success")
        return redirect(url_for("manage_bonus_types"))
    
    return render_template("edit_bonus_type.html", bonus=bonus)


@app.route("/delete_bonus_type/<int:bonus_id>", methods=["POST"])
@login_required
def delete_bonus_type(bonus_id):
    """Xóa loại điểm cộng"""
    bonus = db.session.get(BonusType, bonus_id)
    if bonus:
        db.session.delete(bonus)
        db.session.commit()
        flash("Đã xóa loại điểm cộng!", "success")
    return redirect(url_for("manage_bonus_types"))


@app.route("/add_bonus", methods=["GET", "POST"])
@login_required
def add_bonus():
    """Thêm điểm cộng cho học sinh"""
    if request.method == "POST":
        selected_student_ids = request.form.getlist("student_ids[]")
        selected_bonus_ids = request.form.getlist("bonus_ids[]")
        reason = request.form.get("reason", "").strip()
        
        if not selected_student_ids:
            flash("Vui lòng chọn ít nhất một học sinh!", "error")
            return redirect(url_for("add_bonus"))
        
        if not selected_bonus_ids:
            flash("Vui lòng chọn ít nhất một loại điểm cộng!", "error")
            return redirect(url_for("add_bonus"))
        
        # Lấy tuần hiện tại
        w_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week = int(w_cfg.value) if w_cfg else 1
        
        count = 0
        for bonus_id in selected_bonus_ids:
            bonus_type = db.session.get(BonusType, int(bonus_id))
            if not bonus_type:
                continue
            
            for s_id in selected_student_ids:
                student = db.session.get(Student, int(s_id))
                if student:
                    # Cộng điểm
                    old_score = student.current_score or 100
                    student.current_score = old_score + bonus_type.points_added
                    
                    # Lưu lịch sử
                    db.session.add(BonusRecord(
                        student_id=student.id,
                        bonus_type_name=bonus_type.name,
                        points_added=bonus_type.points_added,
                        reason=reason or None,
                        week_number=current_week
                    ))
                    log_change('bonus', f'Điểm cộng: {bonus_type.name} (+{bonus_type.points_added} điểm){" - " + reason if reason else ""}', student_id=student.id, student_name=student.name, student_class=student.student_class, old_value=old_score, new_value=student.current_score)
                    count += 1
        
        if count > 0:
            db.session.commit()
            flash(f"Đã ghi nhận điểm cộng cho {len(selected_student_ids)} học sinh x {len(selected_bonus_ids)} loại!", "success")
        else:
            flash("Có lỗi xảy ra, không ghi nhận được điểm cộng!", "error")
        
        return redirect(url_for("add_bonus"))
    
    # GET: Render form (filtered by role)
    students = get_accessible_students().order_by(Student.student_class, Student.name).all()
    bonus_types = BonusType.query.order_by(BonusType.points_added.desc()).all()
    return render_template("add_bonus.html", students=students, bonus_types=bonus_types)


# === ADMIN PANEL - QUẢN LÝ GIÁO VIÊN ===

@app.route("/admin/teachers")
@admin_required
def manage_teachers():
    """Danh sách giáo viên - Chỉ Admin"""
    teachers = Teacher.query.filter(Teacher.id != current_user.id).order_by(Teacher.created_at.desc()).all()
    subjects = Subject.query.order_by(Subject.name).all()
    classes = ClassRoom.query.order_by(ClassRoom.name).all()
    return render_template("manage_teachers.html", teachers=teachers, subjects=subjects, classes=classes)


@app.route("/admin/teachers/add", methods=["GET", "POST"])
@admin_required
def add_teacher():
    """Thêm giáo viên mới - Chỉ Admin"""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "homeroom_teacher")
        assigned_class = request.form.get("assigned_class", "").strip() or None
        assigned_subject_id = request.form.get("assigned_subject_id") or None
        
        # Validation
        if not username or not password or not full_name:
            flash("Vui lòng điền đầy đủ thông tin!", "error")
            return redirect(url_for("add_teacher"))
        
        # Check username exists
        if Teacher.query.filter_by(username=username).first():
            flash(f"Username '{username}' đã tồn tại!", "error")
            return redirect(url_for("add_teacher"))
        
        # Create new teacher
        new_teacher = Teacher(
            username=username,
            password=password,  # Note: nên hash password trong production
            full_name=full_name,
            role=role,
            assigned_class=assigned_class if role == "homeroom_teacher" else None,
            assigned_subject_id=int(assigned_subject_id) if role == "subject_teacher" and assigned_subject_id else None,
            created_by=current_user.id
        )
        
        try:
            db.session.add(new_teacher)
            db.session.commit()
            flash(f"Đã tạo tài khoản '{full_name}' thành công!", "success")
            return redirect(url_for("manage_teachers"))
        except Exception as e:
            db.session.rollback()
            flash(f"Lỗi tạo tài khoản: {str(e)}", "error")
            return redirect(url_for("add_teacher"))
    
    # GET: Render form
    subjects = Subject.query.order_by(Subject.name).all()
    classes = ClassRoom.query.order_by(ClassRoom.name).all()
    return render_template("add_teacher.html", subjects=subjects, classes=classes)


@app.route("/admin/teachers/<int:teacher_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_teacher(teacher_id):
    """Sửa thông tin giáo viên - Chỉ Admin"""
    teacher = Teacher.query.get_or_404(teacher_id)
    
    # Không cho sửa chính mình
    if teacher.id == current_user.id:
        flash("Không thể sửa tài khoản của chính mình!", "error")
        return redirect(url_for("manage_teachers"))
    
    if request.method == "POST":
        teacher.full_name = request.form.get("full_name", "").strip() or teacher.full_name
        teacher.role = request.form.get("role", teacher.role)
        
        new_password = request.form.get("password", "").strip()
        if new_password:
            teacher.password = new_password
        
        if teacher.role == "homeroom_teacher":
            teacher.assigned_class = request.form.get("assigned_class", "").strip() or None
            teacher.assigned_subject_id = None
        elif teacher.role == "subject_teacher":
            teacher.assigned_subject_id = request.form.get("assigned_subject_id") or None
            if teacher.assigned_subject_id:
                teacher.assigned_subject_id = int(teacher.assigned_subject_id)
            teacher.assigned_class = None
        else:  # admin
            teacher.assigned_class = None
            teacher.assigned_subject_id = None
        
        try:
            db.session.commit()
            flash(f"Đã cập nhật thông tin '{teacher.full_name}'!", "success")
            return redirect(url_for("manage_teachers"))
        except Exception as e:
            db.session.rollback()
            flash(f"Lỗi cập nhật: {str(e)}", "error")
    
    # GET: Render form
    subjects = Subject.query.order_by(Subject.name).all()
    classes = ClassRoom.query.order_by(ClassRoom.name).all()
    return render_template("edit_teacher.html", teacher=teacher, subjects=subjects, classes=classes)


@app.route("/admin/teachers/<int:teacher_id>/delete", methods=["POST"])
@admin_required
def delete_teacher(teacher_id):
    """Xóa giáo viên - Chỉ Admin"""
    teacher = Teacher.query.get_or_404(teacher_id)
    
    # Không cho xóa chính mình
    if teacher.id == current_user.id:
        flash("Không thể xóa tài khoản của chính mình!", "error")
        return redirect(url_for("manage_teachers"))
    
    # Không cho xóa admin khác
    if teacher.role == "admin":
        flash("Không thể xóa tài khoản Admin!", "error")
        return redirect(url_for("manage_teachers"))
    
    try:
        name = teacher.full_name
        
        # Xóa tất cả tin nhắn group chat của giáo viên này
        GroupChatMessage.query.filter_by(sender_id=teacher_id).delete()
        
        # Xóa tất cả tin nhắn riêng của giáo viên này (cả gửi và nhận)
        PrivateMessage.query.filter(
            or_(
                PrivateMessage.sender_id == teacher_id,
                PrivateMessage.receiver_id == teacher_id
            )
        ).delete()
        
        # Xóa tất cả thông báo liên quan
        Notification.query.filter(
            or_(
                Notification.created_by == teacher_id,
                Notification.recipient_id == teacher_id
            )
        ).delete()
        
        # Cuối cùng xóa tài khoản giáo viên
        db.session.delete(teacher)
        db.session.commit()
        flash(f"Đã xóa tài khoản '{name}'!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi xóa tài khoản: {str(e)}", "error")
    
    return redirect(url_for("manage_teachers"))


# === NOTIFICATION ROUTES ===

@app.route("/admin/send_notification", methods=["GET", "POST"])
@admin_required
def send_notification():
    """Admin gửi thông báo chung"""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        target_role = request.form.get("target_role", "all")
        
        if not title or not message:
            flash("Vui lòng điền đầy đủ thông tin!", "error")
            return redirect(url_for("send_notification"))
        
        try:
            create_notification(title, message, 'announcement', target_role)
            flash("Đã gửi thông báo thành công!", "success")
        except Exception as e:
            flash(f"Lỗi gửi thông báo: {str(e)}", "error")
        
        return redirect(url_for("send_notification"))
    
    return render_template("send_notification.html")

@app.route("/notifications")
@login_required
def notifications():
    """Xem danh sách thông báo"""
    notifs = Notification.query.filter_by(recipient_id=current_user.id)\
        .order_by(Notification.created_at.desc()).all()
    return render_template("notifications.html", notifications=notifs)

@app.route("/api/mark_notification_read/<int:notif_id>", methods=["POST"])
@login_required
def mark_notification_read(notif_id):
    """Đánh dấu thông báo đã đọc"""
    notif = Notification.query.get(notif_id)
    if notif and notif.recipient_id == current_user.id:
        notif.is_read = True
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False}), 403


# === GROUP CHAT ROUTES ===

@app.route("/group_chat")
@login_required
def group_chat():
    """Phòng chat chung"""
    messages = GroupChatMessage.query.order_by(GroupChatMessage.created_at.asc()).limit(100).all()
    return render_template("group_chat.html", messages=messages)

@app.route("/api/group_chat/send", methods=["POST"])
@login_required
def send_group_message():
    """API gửi tin nhắn"""
    message_text = request.json.get("message", "").strip()
    if not message_text:
        return jsonify({"success": False, "error": "Tin nhắn trống"}), 400
    
    msg = GroupChatMessage(
        sender_id=current_user.id,
        message=message_text
    )
    db.session.add(msg)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "sender_name": current_user.full_name,
            "message": msg.message,
            "created_at": msg.created_at.strftime("%H:%M %d/%m")
        }
    })

@app.route("/api/group_chat/messages")
@login_required
def get_group_messages():
    """API lấy danh sách tin nhắn"""
    messages = GroupChatMessage.query.order_by(GroupChatMessage.created_at.asc()).limit(100).all()
    return jsonify({
        "messages": [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "sender_name": m.sender.full_name,
                "message": m.message,
                "created_at": m.created_at.strftime("%H:%M %d/%m")
            }
            for m in messages
        ]
    })


# === PRIVATE CHAT ROUTES ===

@app.route("/private_chats")
@login_required
def private_chats():
    """Danh sách conversations (người đã chat)"""
    # Lấy tất cả tin nhắn mà user tham gia (gửi hoặc nhận)
    messages = PrivateMessage.query.filter(
        or_(
            PrivateMessage.sender_id == current_user.id,
            PrivateMessage.receiver_id == current_user.id
        )
    ).all()
    
    # Tạo dict: other_user_id -> latest_message
    conversations = {}
    for msg in messages:
        other_id = msg.receiver_id if msg.sender_id == current_user.id else msg.sender_id
        if other_id not in conversations or msg.created_at > conversations[other_id]['last_time']:
            unread_count = PrivateMessage.query.filter_by(
                sender_id=other_id,
                receiver_id=current_user.id,
                is_read=False
            ).count()
            conversations[other_id] = {
                'user': Teacher.query.get(other_id),
                'last_message': msg.message,
                'last_time': msg.created_at,
                'unread_count': unread_count
            }
    
    # Sort by last_time
    sorted_convs = sorted(conversations.items(), key=lambda x: x[1]['last_time'], reverse=True)
    
    # Danh sách tất cả giáo viên để chọn chat mới
    all_teachers = Teacher.query.filter(Teacher.id != current_user.id).order_by(Teacher.full_name).all()
    
    return render_template("private_chats.html", conversations=sorted_convs, all_teachers=all_teachers)

@app.route("/private_chat/<int:teacher_id>")
@login_required
def private_chat(teacher_id):
    """Chat với 1 giáo viên cụ thể"""
    other = Teacher.query.get_or_404(teacher_id)
    
    if other.id == current_user.id:
        flash("Không thể chat với chính mình!", "error")
        return redirect(url_for('private_chats'))
    
    # Lấy tất cả tin nhắn giữa 2 người
    messages = PrivateMessage.query.filter(
        or_(
            and_(PrivateMessage.sender_id == current_user.id, PrivateMessage.receiver_id == teacher_id),
            and_(PrivateMessage.sender_id == teacher_id, PrivateMessage.receiver_id == current_user.id)
        )
    ).order_by(PrivateMessage.created_at.asc()).all()
    
    # Đánh dấu tin nhắn của người kia gửi đến mình là đã đọc
    unread = PrivateMessage.query.filter_by(
        receiver_id=current_user.id,
        sender_id=teacher_id,
        is_read=False
    ).all()
    for msg in unread:
        msg.is_read = True
    if unread:
        db.session.commit()
    
    return render_template("private_chat.html", other=other, messages=messages)

@app.route("/api/private_chat/send", methods=["POST"])
@login_required
def send_private_message():
    """API gửi tin nhắn riêng"""
    receiver_id = request.json.get("receiver_id")
    message_text = request.json.get("message", "").strip()
    
    if not receiver_id or not message_text:
        return jsonify({"success": False, "error": "Thiếu thông tin"}), 400
    
    if int(receiver_id) == current_user.id:
        return jsonify({"success": False, "error": "Không thể gửi cho chính mình"}), 400
    
    msg = PrivateMessage(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        message=message_text
    )
    db.session.add(msg)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "sender_name": current_user.full_name,
            "message": msg.message,
            "created_at": msg.created_at.strftime("%H:%M %d/%m")
        }
    })

@app.route("/api/private_chat/messages/<int:teacher_id>")
@login_required
def get_private_messages(teacher_id):
    """API lấy tin nhắn với 1 người"""
    messages = PrivateMessage.query.filter(
        or_(
            and_(PrivateMessage.sender_id == current_user.id, PrivateMessage.receiver_id == teacher_id),
            and_(PrivateMessage.sender_id == teacher_id, PrivateMessage.receiver_id == current_user.id)
        )
    ).order_by(PrivateMessage.created_at.asc()).all()
    
    return jsonify({
        "messages": [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "sender_name": m.sender.full_name,
                "message": m.message,
                "created_at": m.created_at.strftime("%H:%M %d/%m")
            }
            for m in messages
        ]
    })


# === ASSISTANT CHATBOT (ĐA NĂNG) ROUTES ===

@app.route("/assistant_chatbot")
@login_required
def assistant_chatbot():
    """Chatbot đa năng: nội quy, ứng xử, trợ giúp GV"""
    return render_template("assistant_chatbot.html")

@app.route("/api/assistant_chatbot", methods=["POST"])
@login_required
def api_assistant_chatbot():
    """API cho chatbot đa năng với intent detection"""
    msg = request.json.get("message", "").strip()
    
    if not msg:
        return jsonify({"response": "Vui lòng nhập câu hỏi."})
    
    # Import prompts từ file riêng
    from prompts import (
        SCHOOL_RULES_PROMPT, 
        BEHAVIOR_GUIDE_PROMPT, 
        TEACHER_ASSISTANT_PROMPT,
        DEFAULT_ASSISTANT_PROMPT
    )
    
    # Intent detection - phát hiện chủ đề câu hỏi
    msg_lower = msg.lower()
    
    # Kiểm tra từ khóa nội quy
    school_rules_keywords = ["nội quy", "vi phạm", "quy định", "điểm rèn luyện", "bị trừ", "mức phạt", "xử lý kỷ luật"]
    if any(kw in msg_lower for kw in school_rules_keywords):
        system_prompt = SCHOOL_RULES_PROMPT
        category = "nội quy"
    
    # Kiểm tra từ khóa ứng xử
    elif any(kw in msg_lower for kw in ["ứng xử", "cách xử lý", "tình huống", "kỹ năng", "giao tiếp", "cãi nhau", "đánh nhau", "bắt nạt"]):
        system_prompt = BEHAVIOR_GUIDE_PROMPT
        category = "ứng xử"
    
    # Kiểm tra từ khóa trợ giúp giáo viên
    elif any(kw in msg_lower for kw in ["nhận xét", "viết nhận xét", "đánh giá học sinh", "soạn", "phương pháp", "quản lý lớp", "giáo dục", "động viên"]):
        system_prompt = TEACHER_ASSISTANT_PROMPT
        category = "trợ giúp GV"
    
    # Mặc định
    else:
        system_prompt = DEFAULT_ASSISTANT_PROMPT
        category = "general"
    
    # Tạo full prompt
    full_prompt = f"""{system_prompt}

===== CÂU HỎI =====
{msg}

===== YÊU CẦU =====
Trả lời ngắn gọn, rõ ràng bằng tiếng Việt. Sử dụng markdown và emoji phù hợp."""
    
    # Gọi Ollama
    answer, err = call_ollama(full_prompt)
    
    if err:
        response_text = f"⚠️ {err}\n\nVui lòng kiểm tra:\n• Ollama đã được cài đặt và chạy chưa?\n• Model đã được pull chưa? (`ollama pull gemini-3-flash-preview`)"
    else:
        response_text = answer or "Xin lỗi, tôi không thể trả lời câu hỏi này."
    
    return jsonify({
        "response": response_text,
        "category": category
    })


if __name__ == "__main__":
    app.run(debug=True)
 
