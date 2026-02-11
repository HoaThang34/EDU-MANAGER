from app import app, db, Student

with app.app_context():
    count = Student.query.count()
    print(f"Total students in DB: {count}")
    
    if count > 0:
        first_student = Student.query.first()
        print(f"Sample: {first_student.name} - {first_student.student_class} - {first_student.student_code}")
