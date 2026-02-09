# -*- coding: utf-8 -*-
"""
Import students from Excel file (data/student_dataset.xlsx) into the database
Standalone script that doesn't trigger Flask app.run()
"""
import os
import sys
import pandas as pd

# Set up path for import
basedir = os.path.abspath(os.path.dirname(__file__))

# Import only the models and db, not the entire app to avoid triggering app.run()
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from models import db, Student, ClassRoom

# Create a minimal Flask app just for database operations
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

def import_students_from_excel(filepath):
    """
    Import students from Excel file to database
    
    Args:
        filepath: Path to the Excel file
    
    Returns:
        tuple: (success_count, skipped_count, errors)
    """
    print(f"Reading file: {filepath}")
    df = pd.read_excel(filepath)
    
    success_count = 0
    skipped_count = 0
    errors = []
    
    # Column mapping from Vietnamese to English
    # Mã học sinh -> student_code
    # Họ và tên -> name
    # Lớp -> student_class
    
    with app.app_context():
        for index, row in df.iterrows():
            try:
                student_code = str(row['Mã học sinh']).strip()
                name = str(row['Họ và tên']).strip()
                student_class = str(row['Lớp']).strip()
                
                # Skip empty rows
                if not student_code or not name or student_code == 'nan':
                    skipped_count += 1
                    continue
                
                # Check for duplicate student_code
                existing = Student.query.filter_by(student_code=student_code).first()
                if existing:
                    skipped_count += 1
                    continue
                
                # Create ClassRoom if not exists
                classroom = ClassRoom.query.filter_by(name=student_class).first()
                if not classroom:
                    classroom = ClassRoom(name=student_class)
                    db.session.add(classroom)
                    print(f"  Created class: {student_class}")
                
                # Create student with default score of 100
                student = Student(
                    name=name,
                    student_code=student_code,
                    student_class=student_class,
                    current_score=100
                )
                db.session.add(student)
                success_count += 1
                
                # Commit every 100 students
                if success_count % 100 == 0:
                    db.session.commit()
                    print(f"  Imported {success_count} students...")
                    
            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")
        
        # Final commit
        db.session.commit()
    
    return success_count, skipped_count, errors

if __name__ == "__main__":
    excel_path = os.path.join(basedir, "data", "student_dataset.xlsx")
    
    if not os.path.exists(excel_path):
        print(f"Error: File not found: {excel_path}")
        sys.exit(1)
    
    print("=" * 50)
    print("EDU-MANAGER: Student Import Tool")
    print("=" * 50)
    
    success, skipped, errors = import_students_from_excel(excel_path)
    
    print("\n" + "=" * 50)
    print("IMPORT RESULTS:")
    print(f"  - Successfully imported: {success} students")
    print(f"  - Skipped (duplicate/empty): {skipped} students")
    print(f"  - Errors: {len(errors)}")
    
    if errors:
        print("\nErrors details:")
        for err in errors[:10]:  # Show first 10 errors
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
    
    print("=" * 50)
    print("Done!")
