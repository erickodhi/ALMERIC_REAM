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
    session,
)
from models import Form, Student, Stream, StaffUser, ReamRecord, SystemSetting, ExamRequest, SheetDisbursement, db

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
    # Ensure system setting exists
    system_setting = SystemSetting.query.first()
    if not system_setting:
        system_setting = SystemSetting(active_year='2026', active_term='Term 1')
        db.session.add(system_setting)
        db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'set_active_period':
            active_year = request.form.get('active_year')
            active_term = request.form.get('active_term')
            if active_year and active_term:
                system_setting.active_year = active_year.strip()
                system_setting.active_term = active_term.strip()
                db.session.commit()
                flash(f'Active collection period locked to {active_term}, {active_year} successfully!', 'success')
            return redirect(url_for('admin_dashboard'))

        elif action == 'add_form':
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
        selected_year=selected_year,
        system_setting=system_setting
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
        'Form 4': 'Alumni',
        'Grade 10': 'Grade 11',
        'Grade 11': 'Grade 12',
        'Grade 12': 'Alumni'
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
        
        if action in ['create_staff', 'add_staff']:
            username = request.form.get('username')
            full_name = request.form.get('full_name', '')
            password = request.form.get('password')
            role = request.form.get('role')

            if username:
                username = username.strip()
            if password:
                password = password.strip()
            if role:
                role = role.strip()

            existing = StaffUser.query.filter_by(username=username).first()
            if existing:
                flash(f'Username "{username}" already exists. Choose a different one.', 'danger')
            else:
                new_staff = StaffUser(
                    username=username, 
                    full_name=full_name.strip() if full_name else username,
                    password=password, 
                    role=role
                )
                db.session.add(new_staff)
                db.session.commit()
                flash('Staff account created successfully!', 'success')
                
        elif action in ['delete_staff', 'delete']:
            staff_id = request.form.get('staff_id')
            if staff_id:
                staff_member = StaffUser.query.get_or_404(staff_id)
                db.session.delete(staff_member)
                db.session.commit()
                flash('Staff account deleted successfully.', 'success')

        elif action == 'reset_password':
            staff_id = request.form.get('staff_id')
            new_password = request.form.get('new_password')
            if staff_id and new_password:
                staff = StaffUser.query.get_or_404(staff_id)
                staff.password = new_password.strip()
                db.session.commit()
                flash(f'Password reset successfully!', 'success')
            
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


# ==========================================
# STAFF LOGIN & PORTAL ROUTES
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username:
            username = username.strip()
        if password:
            password = password.strip()
            
        staff = StaffUser.query.filter_by(username=username, password=password).first()
        if staff:
            session['user_id'] = staff.id
            session['username'] = staff.username
            session['role'] = staff.role
            flash(f'Logged in successfully as {staff.role}', 'success')
            
            # Smart role-based redirection to their specific page
            role_str = staff.role.lower()
            if 'head' in role_str or 'hoi' in role_str:
                return redirect(url_for('hoi_dashboard'))
            elif 'ream' in role_str or 'collection' in role_str or 'collector' in role_str:
                return redirect(url_for('ream_dashboard'))
            elif 'exam' in role_str:
                return redirect(url_for('exam_office'))
            else:
                return redirect(url_for('ream_dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')


@app.route('/portal/hoi')
def hoi_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))
    return render_template('under_construction.html', role="Head of Institution (HOI)", username=session.get('username'))


@app.route('/portal/ream', methods=['GET', 'POST'])
def ream_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    # Fetch active term and year globally configured by Admin
    setting = SystemSetting.query.first()
    selected_year = setting.active_year if setting else '2026'
    selected_term = setting.active_term if setting else 'Term 1'
    
    page = request.args.get('page', 1, type=int)
    term_map = {'Term 1': 1, 'Term 2': 2, 'Term 3': 3}

    if request.method == 'POST':
        action = request.form.get('action')
        student_id = request.form.get('student_id')
        
        student = Student.query.get(student_id)
        if student:
            student_term_num = term_map.get(student.enrollment_term, 1)
            current_term_num = term_map.get(selected_term, 1)
            is_exempt = current_term_num < student_term_num

            if not is_exempt:
                if action == 'submit':
                    existing = ReamRecord.query.filter_by(student_id=student_id, term=selected_term, year=selected_year).first()
                    if not existing:
                        new_record = ReamRecord(
                            student_id=student_id,
                            term=selected_term,
                            year=selected_year,
                            reams_count=1,
                            received_by=session.get('username')
                        )
                        db.session.add(new_record)
                        db.session.commit()
                        flash(f'Ream marked as submitted for {student.full_name}.', 'success')
                elif action == 'undo':
                    record = ReamRecord.query.filter_by(student_id=student_id, term=selected_term, year=selected_year).first()
                    if record:
                        db.session.delete(record)
                        db.session.commit()
                        flash(f'Submission undone for {student.full_name}.', 'info')
                        
        return redirect(url_for('ream_dashboard', page=page))

    # Pagination: exactly 15 students per page matching the active year
    pagination = Student.query.filter_by(year=selected_year).order_by(Student.adm_no).paginate(page=page, per_page=15, error_out=False)
    students = pagination.items

    # Fetch ream records for these 15 students
    student_ids = [s.id for s in students]
    records = ReamRecord.query.filter(ReamRecord.student_id.in_(student_ids), ReamRecord.year==selected_year).all()
    
    # Map statuses for all 3 terms per student
    ream_statuses = {s.id: {'Term 1': False, 'Term 2': False, 'Term 3': False} for s in students}
    for r in records:
        if r.student_id in ream_statuses and r.term in ream_statuses[r.student_id]:
            ream_statuses[r.student_id][r.term] = True

    return render_template(
        'ream_dashboard.html',
        role="Ream Collection Desk",
        username=session.get('username'),
        pagination=pagination,
        students=students,
        ream_statuses=ream_statuses,
        term_map=term_map,
        selected_year=selected_year,
        selected_term=selected_term
    )


@app.route('/portal/exam')
def exam_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))
    return redirect(url_for('exam_office'))


@app.route('/portal')
def staff_portal():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))
    return render_template('under_construction.html', role=session.get('role'), username=session.get('username'))


@app.route('/examination-office', methods=['GET', 'POST'])
def exam_office():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    # 1. Calculate total reams collected in store
    total_reams_collected = db.session.query(db.func.sum(ReamRecord.reams_count)).scalar() or 0
    total_store_sheets = total_reams_collected * 500

    # Calculate total sheets already requested/taken from store
    total_sheets_requested = db.session.query(db.func.sum(ExamRequest.total_sheets_needed)).scalar() or 0
    
    # Ensure available store sheets never drop below 0
    available_store_sheets = max(0, total_store_sheets - total_sheets_requested)

    # Calculate current undisbursed loose leftover sheets across requests
    total_loose_generated = db.session.query(db.func.sum(ExamRequest.loose_leftover_sheets)).scalar() or 0
    total_loose_disbursed = db.session.query(db.func.sum(SheetDisbursement.disbursed_sheets)).scalar() or 0
    active_loose_sheets = total_loose_generated - total_loose_disbursed

    if request.method == 'POST':
        action = request.form.get('action')

        # Guardrail 1: Check if any ream is collected yet
        if total_reams_collected <= 0:
            flash("STORE STATUS ERROR: NO REAM COLLECTED YET. Please wait for collection desk.", "error")
            return redirect(url_for('exam_office'))

        # Guardrail 2: Check if active loose sheets exceed 20
        if action == 'request_reams' and active_loose_sheets > 20:
            flash("REQUEST DENIED: ACTIVE LOOSE LEFTOVER SHEETS EXCEED 20. You must disburse loose sheets first.", "error")
            return redirect(url_for('exam_office'))

        if action == 'request_reams':
            subject = request.form.get('subject')
            purpose = request.form.get('purpose')
            target_form = request.form.get('target_form')
            stream = request.form.get('stream')
            num_students = int(request.form.get('num_students'))
            sheets_per_student = int(request.form.get('sheets_per_student'))

            raw_needed = num_students * sheets_per_student

            # Apply custom padding rule
            padding = 60 if raw_needed <= 250 else 50
            total_needed_with_padding = raw_needed + padding

            # Guardrail 3: Check if requesting more than available store sheets
            if total_needed_with_padding > available_store_sheets:
                flash("REQUESTING MORE THAN IS AVAILABLE IN THE STORE.", "error")
                return redirect(url_for('exam_office'))

            # Calculate reams and loose leftover sheets
            reams_to_take = total_needed_with_padding // 500
            loose_leftover = total_needed_with_padding % 500

            new_req = ExamRequest(
                subject=subject,
                purpose=purpose,
                target_form=target_form,
                stream=stream,
                num_students=num_students,
                sheets_per_student=sheets_per_student,
                total_sheets_needed=total_needed_with_padding,
                padding_sheets=padding,
                loose_leftover_sheets=loose_leftover,
                reams_allocated=reams_to_take if reams_to_take > 0 else 1
            )
            db.session.add(new_req)
            db.session.commit()
            flash("Exam ream request verified and recorded successfully!", "success")
            return redirect(url_for('exam_office'))

        elif action == 'disburse_sheets':
            subject = request.form.get('subject')
            purpose = request.form.get('purpose')
            target_form = request.form.get('target_form')
            stream = request.form.get('stream')
            num_students = int(request.form.get('num_students'))
            sheets_per_student = int(request.form.get('sheets_per_student'))
            disbursed_total = num_students * sheets_per_student

            # Guardrail: Prevent disbursing more loose sheets than are currently active/available
            if disbursed_total > active_loose_sheets:
                flash(f"DISBURSEMENT DENIED: Cannot disburse {disbursed_total} sheets. You only have {active_loose_sheets} active loose leftover sheets available.", "error")
                return redirect(url_for('exam_office'))

            new_disb = SheetDisbursement(
                subject=subject,
                purpose=purpose,
                target_form=target_form,
                stream=stream,
                num_students=num_students,
                sheets_per_student=sheets_per_student,
                disbursed_sheets=disbursed_total
            )
            db.session.add(new_disb)
            db.session.commit()
            flash("Loose leftover sheets disbursed successfully!", "success")
            return redirect(url_for('exam_office'))

    exam_requests = ExamRequest.query.order_by(ExamRequest.created_at.desc()).all()
    disbursements = SheetDisbursement.query.order_by(SheetDisbursement.created_at.desc()).all()

    return render_template(
        'examination_office.html',
        exam_requests=exam_requests,
        disbursements=disbursements,
        total_reams_collected=total_reams_collected,
        available_store_sheets=available_store_sheets,
        active_loose_sheets=active_loose_sheets
    )


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/')
def index():
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    app.run(debug=True)