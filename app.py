import os
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from models import Form, Student, Stream, db

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///ream_system.db'
)
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY', 'almeric_ream_secret_key'
)

db.init_app(app)

with app.app_context():
    db.create_all()


@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_form':
            form_name = request.form.get('form_name')
            if form_name:
                existing = Form.query.filter_by(name=form_name).first()
                if not existing:
                    new_form = Form(name=form_name)
                    db.session.add(new_form)
                    db.session.commit()
                    flash(f'Form "{form_name}" created successfully!', 'success')
                else:
                    flash(f'Form "{form_name}" already exists.', 'danger')
            return redirect(url_for('admin_dashboard'))

        elif action == 'add_stream':
            form_id = request.form.get('form_id')
            stream_name = request.form.get('stream_name')
            if form_id and stream_name:
                new_stream = Stream(name=stream_name, form_id=form_id)
                db.session.add(new_stream)
                db.session.commit()
                flash(f'Stream "{stream_name}" added successfully!', 'success')
            return redirect(url_for('admin_dashboard'))

        elif action == 'enroll_student':
            adm_no = request.form.get('adm_no')
            full_name = request.form.get('full_name')
            form = request.form.get('form')
            stream = request.form.get('stream')
            gender = request.form.get('gender')
            enrollment_term = request.form.get('enrollment_term')
            year = request.form.get('year')

            if adm_no and full_name and form and stream:
                existing_student = Student.query.filter_by(adm_no=adm_no).first()
                if existing_student:
                    flash(f'Student with admission number {adm_no} already exists.', 'danger')
                else:
                    new_student = Student(
                        adm_no=adm_no,
                        full_name=full_name,
                        form=form,
                        stream=stream,
                        gender=gender,
                        enrollment_term=enrollment_term,
                        year=year
                    )
                    db.session.add(new_student)
                    db.session.commit()
                    flash(f'Student {full_name} enrolled successfully!', 'success')
            return redirect(url_for('admin_dashboard'))

    forms = Form.query.all()
    students = Student.query.all()
    
    # Ensure streams are explicitly queried/loaded for each form object
    for form in forms:
        if not hasattr(form, 'streams') or not form.streams:
            form.streams = Stream.query.filter_by(form_id=form.id).all()

    return render_template('admin.html', forms=forms, students=students)

@app.route('/admin/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    flash('Student record deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/download_template')
def download_template():
    csv_content = (
        'Admission Number,Full Name,Form/Grade,Stream,Gender,Term of'
        ' Enrollment,Year\n'
    )
    csv_content += (
        'ADM001,John Doe,Form 1,East,Male,Term 1,2026\nADM002,Jane Smith,Form'
        ' 1,West,Female,Term 2,2026\n'
    )
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={
            'Content-Disposition': 'attachment;filename=student_bulk_template.csv'
        },
    )

import csv
import io

@app.route('/admin/upload_csv', methods=['POST'])
def upload_csv():
    if 'csv_file' not in request.files:
        flash('No file uploaded.', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['csv_file']
    if file.filename == '':
        flash('No selected file.', 'danger')
        return redirect(url_for('admin_dashboard'))

    if file and file.filename.endswith('.csv'):
        try:
            stream = io.TextIOWrapper(file.stream, encoding='utf-8')
            csv_reader = csv.DictReader(stream)
            
            success_count = 0
            duplicate_count = 0

            for row in csv_reader:
                adm_no = row.get('Admission Number', '').strip()
                full_name = row.get('Full Name', '').strip()
                form = row.get('Form/Grade', '').strip()
                stream_name = row.get('Stream', '').strip()
                gender = row.get('Gender', 'Male').strip()
                enrollment_term = row.get('Term of Enrollment', 'Term 1').strip()
                year = row.get('Year', '2026').strip()

                if adm_no and full_name and form and stream_name:
                    existing = Student.query.filter_by(adm_no=adm_no).first()
                    if not existing:
                        new_student = Student(
                            adm_no=adm_no,
                            full_name=full_name,
                            form=form,
                            stream=stream_name,
                            gender=gender,
                            enrollment_term=enrollment_term,
                            year=year
                        )
                        db.session.add(new_student)
                        success_count += 1
                    else:
                        duplicate_count += 1

            db.session.commit()
            flash(f'Successfully imported {success_count} students! ({duplicate_count} duplicates skipped).', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing CSV file: {str(e)}', 'danger')
    else:
        flash('Please upload a valid .csv file.', 'danger')

    return redirect(url_for('admin_dashboard'))


@app.route('/')
def index():
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    app.run(debug=True)