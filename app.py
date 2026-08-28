import csv
import io
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
from models import StaffUser  # Ensure StaffUser is imported at the top with your other models

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
            year = request.form.get('year', '2026')

            existing_student = Student.query.filter_by(adm_no=adm_no, year=year).first()
            if existing_student:
                flash(f'Student with admission number {adm_no} already exists in year {year}.', 'danger')
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

    # Get all available distinct years for the filter dropdown
    year_results = db.session.query(Student.year.distinct()).all()
    available_years = [y[0] for y in year_results] if year_results else ['2026']
    available_years = sorted(list(set(available_years)))

    # Selected year filter query parameter (defaults to the latest or '2026')
    selected_year = request.args.get('year', available_years[-1] if available_years else '2026')

    forms = Form.query.all()
    students = Student.query.filter_by(year=selected_year).all()
    
    # Ensure streams are explicitly queried/loaded for each form object
    for form in forms:
        if not hasattr(form, 'streams') or not form.streams:
            form.streams = Stream.query.filter_by(form_id=form.id).all()

    return render_template(
        'admin.html', 
        forms=forms, 
        students=students, 
        available_years=available_years, 
        selected_year=selected_year
    )


@app.route('/admin/promote', methods=['POST'])
def promote_students():
    source_year = request.form.get('source_year')
    target_year = request.form.get('target_year')

    if not source_year or not target_year:
        flash('Please specify both source and target academic years.', 'danger')
        return redirect(url_for('admin_dashboard'))

    source_students = Student.query.filter_by(year=source_year).all()
    
    if not source_students:
        flash(f'No students found in year {source_year} to promote.', 'warning')
        return redirect(url_for('admin_dashboard'))

    promoted_count = 0
    form_progression = {
        'Form 1': 'Form 2',
        'Form 2': 'Form 3',
        'Form 3': 'Form 4',
        'Form 4': 'Alumni'
    }

    for s in source_students:
        existing_target = Student.query.filter_by(adm_no=s.adm_no, year=target_year).first()
        if existing_target:
            continue

        next_form = form_progression.get(s.form, s.form)
        if next_form == 'Alumni':
            continue

        new_student = Student(
            adm_no=s.adm_no,
            full_name=s.full_name,
            form=next_form,
            stream=s.stream,
            gender=s.gender,
            enrollment_term='Term 1',
            year=target_year
        )
        db.session.add(new_student)
        promoted_count += 1

    db.session.commit()
    flash(f'Successfully promoted {promoted_count} students from {source_year} to {target_year}!', 'success')
    return redirect(url_for('admin_dashboard'))


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
                    existing = Student.query.filter_by(adm_no=adm_no, year=year).first()
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

@app.route('/admin/staff', methods=['GET', 'POST'])
def manage_staff():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_staff':
            username = request.form.get('username').strip()
            full_name = request.form.get('full_name').strip()
            password = request.form.get('password').strip()
            role = request.form.get('role').strip()

            existing = StaffUser.query.filter_by(username=username).first()
            if existing:
                flash(f'Username "{username}" is already taken.', 'danger')
            else:
                new_staff = StaffUser(
                    username=username,
                    full_name=full_name,
                    password=password,
                    role=role
                )
                db.session.add(new_staff)
                db.session.commit()
                flash(f'Account for {full_name} ({role}) created successfully!', 'success')
            return redirect(url_for('manage_staff'))

        elif action == 'reset_password':
            staff_id = request.form.get('staff_id')
            new_password = request.form.get('new_password').strip()
            
            staff = StaffUser.query.get_or_404(staff_id)
            staff.password = new_password
            db.session.commit()
            flash(f'Password for {staff.full_name} reset successfully!', 'success')
            return redirect(url_for('manage_staff'))

    staff_members = StaffUser.query.all()
    return render_template('manage_staff.html', staff_members=staff_members)


@app.route('/admin/staff/delete/<int:staff_id>', methods=['POST'])
def delete_staff(staff_id):
    staff = StaffUser.query.get_or_404(staff_id)
    db.session.delete(staff)
    db.session.commit()
    flash('Staff account deleted successfully.', 'success')
    return redirect(url_for('manage_staff'))

@app.route('/admin/staff', methods=['GET', 'POST'])
def manage_staff():
    # Make sure to protect this route with an admin check if you have session tracking set up
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_staff':
            username = request.form.get('username')
            password = request.form.get('password')
            role = request.form.get('role')
            
            existing = StaffUser.query.filter_by(username=username).first()
            if existing:
                flash('Username already exists. Choose a different one.', 'danger')
            else:
                new_staff = StaffUser(username=username, password=password, role=role)
                db.session.add(new_staff)
                db.session.commit()
                flash('Staff account created successfully!', 'success')
                
        elif action == 'delete_staff':
            staff_id = request.form.get('staff_id')
            staff_member = StaffUser.query.get_or_404(staff_id)
            db.session.delete(staff_member)
            db.session.commit()
            flash('Staff account deleted successfully.', 'success')
            
        return redirect(url_for('manage_staff'))

    staff_members = StaffUser.query.all()
    return render_template('manage_staff.html', staff_members=staff_members)
    

@app.route('/')
def index():
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    app.run(debug=True)