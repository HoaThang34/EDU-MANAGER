from app import app, db, Teacher

with app.app_context():
    admin = Teacher.query.filter_by(username="admin").first()
    if admin:
        print(f"Updating user {admin.username} from {admin.role} to admin")
        admin.role = "admin"
        db.session.commit()
        print("Update successful.")
    else:
        print("User 'admin' not found.")
