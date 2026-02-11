from app import app, db, Teacher

with app.app_context():
    admin = Teacher.query.filter_by(username="admin").first()
    if admin:
        print(f"User: {admin.username}")
        print(f"Role: {admin.role}")
        print(f"Assigned Class: {admin.assigned_class}")
        print(f"Assigned Subject: {admin.assigned_subject_id}")
    else:
        print("User 'admin' not found.")
