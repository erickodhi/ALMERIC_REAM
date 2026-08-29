from flask_sqlalchemy import SQLAlchemy
from datetime import datetime


db = SQLAlchemy()

class Form(db.Model):
    __tablename__ = 'form'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    streams = db.relationship('Stream', backref='form_ref', lazy=True, cascade='all, delete-orphan')

class Stream(db.Model):
    __tablename__ = 'stream'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    form_id = db.Column(db.Integer, db.ForeignKey('form.id'), nullable=False)

class Student(db.Model):
    __tablename__ = 'student'
    id = db.Column(db.Integer, primary_key=True)
    adm_no = db.Column(db.String(50), nullable=False)  # Removed unique=True here
    full_name = db.Column(db.String(100), nullable=False)
    form = db.Column(db.String(50), nullable=False)
    stream = db.Column(db.String(50), nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    enrollment_term = db.Column(db.String(20), nullable=False)
    year = db.Column(db.String(10), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('adm_no', 'year', name='uq_adm_year'),
    )

    def get_term_statuses(self):
        term_map_num = {'Term 1': 1, 'Term 2': 2, 'Term 3': 3}
        student_enrol_num = term_map_num.get(self.enrollment_term, 1)

        statuses = {}
        for term_name, t_key in [('Term 1', 't1'), ('Term 2', 't2'), ('Term 3', 't3')]:
            t_num = term_map_num[term_name]
            if t_num < student_enrol_num:
                statuses[t_key] = 'Exempted'
            else:
                # Check if a ReamRecord exists for this student, term, and year
                record = ReamRecord.query.filter_by(
                    student_id=self.id, 
                    term=term_name, 
                    year=self.year
                ).first()
                
                if record:
                    statuses[t_key] = 'Submitted'
                else:
                    statuses[t_key] = 'Pending'
        return statuses

    def get_reams_owed(self):
        statuses = self.get_term_statuses()
        return sum(1 for status in statuses.values() if status == 'Pending')

class StaffUser(db.Model):
    __tablename__ = 'staff_user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(30), nullable=False)  # 'HOI', 'Ream Collection', 'Examination'

class ReamRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    term = db.Column(db.String(20), nullable=False)      # e.g., 'Term 1'
    year = db.Column(db.String(10), nullable=False)      # e.g., '2026'
    reams_count = db.Column(db.Integer, nullable=False, default=1)
    date_collected = db.Column(db.DateTime, default=db.func.current_timestamp())
    received_by = db.Column(db.String(100), nullable=False) # Staff username

    student = db.relationship('Student', backref=db.backref('ream_records', lazy=True, cascade='all, delete-orphan'))

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    active_year = db.Column(db.String(10), default='2026')
    active_term = db.Column(db.String(20), default='Term 1')


class ExamRequest(db.Model):
    __tablename__ = 'exam_request'
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    purpose = db.Column(db.String(150), nullable=False)
    target_form = db.Column(db.String(50), nullable=False)
    stream = db.Column(db.String(50), nullable=False)
    num_students = db.Column(db.Integer, nullable=False)
    sheets_per_student = db.Column(db.Integer, nullable=False)
    total_sheets_needed = db.Column(db.Integer, nullable=False)
    padding_sheets = db.Column(db.Integer, default=0)
    loose_leftover_sheets = db.Column(db.Integer, default=0)
    reams_allocated = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='Approved') # Approved, Disbursed, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SheetDisbursement(db.Model):
    __tablename__ = 'sheet_disbursement'
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    purpose = db.Column(db.String(150), nullable=False)
    target_form = db.Column(db.String(50), nullable=False)
    stream = db.Column(db.String(50), nullable=False)
    num_students = db.Column(db.Integer, nullable=False)
    sheets_per_student = db.Column(db.Integer, nullable=False)
    disbursed_sheets = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)