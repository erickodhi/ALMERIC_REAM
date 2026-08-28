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
    adm_no = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    form = db.Column(db.String(50), nullable=False)
    stream = db.Column(db.String(50), nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    enrollment_term = db.Column(db.String(20), nullable=False)  # 'Term 1', 'Term 2', or 'Term 3'
    year = db.Column(db.String(10), nullable=False)

    def get_term_statuses(self):
        term = self.enrollment_term
        if term == 'Term 2':
            return {'t1': 'Exempted', 't2': 'Pending', 't3': 'Pending'}
        elif term == 'Term 3':
            return {'t1': 'Exempted', 't2': 'Exempted', 't3': 'Pending'}
        else:
            # Enrolled in Term 1
            return {'t1': 'Pending', 't2': 'Pending', 't3': 'Pending'}

    def get_reams_owed(self):
        statuses = self.get_term_statuses()
        # Each pending term requires 1 ream
        return sum(1 for status in statuses.values() if status == 'Pending')