from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import datetime

db = SQLAlchemy()


class ClassRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class SystemConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(50), nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Teacher(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    school_name = db.Column(db.String(150), default="THPT Chuyên Nguyễn Tất Thành")
    main_class = db.Column(db.String(20), default="12 Tin")
    dob = db.Column(db.String(20))
    
    # Hệ thống phân quyền
    role = db.Column(db.String(20), default="homeroom_teacher")  # admin, homeroom_teacher, subject_teacher
    assigned_class = db.Column(db.String(50))  # Lớp được phân công (cho GVCN)
    assigned_subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'))  # Môn được phân công (cho GVBM)
    created_by = db.Column(db.Integer, db.ForeignKey('teacher.id'))  # Admin tạo tài khoản này
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
    assigned_subject = db.relationship('Subject', backref='teachers', foreign_keys=[assigned_subject_id])


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    student_class = db.Column(db.String(20), nullable=False)
    current_score = db.Column(db.Integer, default=100)


class ViolationType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    points_deducted = db.Column(db.Integer, nullable=False)


class Violation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    violation_type_name = db.Column(db.String(200), nullable=False)
    points_deducted = db.Column(db.Integer, nullable=False)
    date_committed = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    week_number = db.Column(db.Integer, default=1)
    student = db.relationship('Student', backref=db.backref('violations', lazy=True))


class WeeklyArchive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week_number = db.Column(db.Integer, nullable=False)
    student_id = db.Column(db.Integer, nullable=True)
    student_name = db.Column(db.String(100))
    student_code = db.Column(db.String(50))
    student_class = db.Column(db.String(20))
    final_score = db.Column(db.Integer)
    total_deductions = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.String(200))
    num_tx_columns = db.Column(db.Integer, default=3)
    num_gk_columns = db.Column(db.Integer, default=1)
    num_hk_columns = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    grade_type = db.Column(db.String(10), nullable=False)
    column_index = db.Column(db.Integer, default=1)
    score = db.Column(db.Float, nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    school_year = db.Column(db.String(20))
    date_recorded = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    student = db.relationship('Student', backref=db.backref('grades', lazy=True, cascade='all, delete-orphan'))
    subject = db.relationship('Subject', backref=db.backref('grades', lazy=True, cascade='all, delete-orphan'))


class ChatConversation(db.Model):
    """Model lưu trữ lịch sử hội thoại chatbot với context awareness"""
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' hoặc 'assistant'
    message = db.Column(db.Text, nullable=False)
    context_data = db.Column(db.Text, nullable=True)  # JSON metadata (student_id, etc.)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    
    teacher = db.relationship('Teacher', backref=db.backref('chat_history', lazy=True))


class BonusType(db.Model):
    """Loại điểm cộng (VD: Tham gia cuộc thi HSG, Tiến bộ học tập, Hoạt động ngoại khóa)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    points_added = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(500))


class BonusRecord(db.Model):
    """Lịch sử điểm cộng của học sinh"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    bonus_type_name = db.Column(db.String(200), nullable=False)
    points_added = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(500))  # Lý do cụ thể (VD: "Giải nhì HSG Toán cấp Tỉnh")
    date_awarded = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    week_number = db.Column(db.Integer, default=1)
    student = db.relationship('Student', backref=db.backref('bonuses', lazy=True))


class Notification(db.Model):
    """Hệ thống thông báo"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('teacher.id'))  # Admin who created
    notification_type = db.Column(db.String(50))  # 'violation', 'grade', 'bonus', 'announcement'
    target_role = db.Column(db.String(50))  # 'all', 'homeroom_teacher', 'subject_teacher', or specific class
    is_read = db.Column(db.Boolean, default=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('teacher.id'))  # Who receives this
    
    creator = db.relationship('Teacher', foreign_keys=[created_by], backref='sent_notifications')
    recipient = db.relationship('Teacher', foreign_keys=[recipient_id], backref='notifications')


class GroupChatMessage(db.Model):
    """Tin nhắn trong phòng chat chung"""
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
    sender = db.relationship('Teacher', backref='group_messages')


class PrivateMessage(db.Model):
    """Tin nhắn riêng tư giữa 2 giáo viên"""
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    
    sender = db.relationship('Teacher', foreign_keys=[sender_id], backref='sent_private_messages')
    receiver = db.relationship('Teacher', foreign_keys=[receiver_id], backref='received_private_messages')


class ChangeLog(db.Model):
    """Lịch sử thay đổi CSDL - ghi nhận mọi thay đổi về điểm, vi phạm, điểm cộng"""
    id = db.Column(db.Integer, primary_key=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=True)
    change_type = db.Column(db.String(50), nullable=False)  # 'violation', 'bonus', 'grade', 'grade_update', 'grade_delete', 'violation_delete', 'score_reset', 'bulk_violation'
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=True)
    student_name = db.Column(db.String(100))
    student_class = db.Column(db.String(20))
    description = db.Column(db.Text, nullable=False)
    old_value = db.Column(db.String(200))
    new_value = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    changed_by = db.relationship('Teacher', backref=db.backref('change_logs', lazy=True))
    student = db.relationship('Student', backref=db.backref('change_logs', lazy=True))