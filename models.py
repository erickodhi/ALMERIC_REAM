from flask_sqlalchemy import SQLAlchemy

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
        term = self.enrollment_term
        if term == 'Term 2':
            return {'t1': 'Exempted', 't2': 'Pending', 't3': 'Pending'}
        elif term == 'Term 3':
            return {'t1': 'Exempted', 't2': 'Exempted', 't3': 'Pending'}
        else:
            return {'t1': 'Pending', 't2': 'Pending', 't3': 'Pending'}

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

    student = db.relationship('Student', backref=db.backref('ream_records', lazy=True))