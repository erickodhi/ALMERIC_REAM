import csv
import io
import os
import math
import africastalking
from datetime import timedelta
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
from models import Form, Student, Stream, StaffUser, ReamRecord, SystemSetting, ExamRequest, SheetDisbursement, AuditLog, db

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///ream_system.db'
)
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY', 'almeric_ream_secret_key'
)

# Automatically expire sessions after 15 minutes of inactivity to prevent attribution mix-ups on shared computers
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)

@app.before_request
def make_session_permanent():
    session.permanent = True
    session.modified = True

db.init_app(app)
with app.app_context():
    db.create_all()
    
    # Auto-seed initial admin account if no staff users exist
    if not StaffUser.query.first():
        admin_user = StaffUser(
            username='admin',
            full_name='System Administrator',
            password='adminpassword123',
            role='Admin'
        )
        db.session.add(admin_user)
        db.session.commit()
        print("Default admin account created: username 'admin' with password 'adminpassword123'")

def log_audit(action_type, details, target="System"):
    """Helper function to anchor audit logs directly to the verified database user record."""
    try:
        current_user = "System Operator"
        user_id = session.get('user_id')
        
        # Pull the exact, unalterable username straight from the database record using user_id
        if user_id:
            staff_member = StaffUser.query.get(user_id)
            if staff_member and staff_member.username:
                current_user = staff_member.username.strip()
        elif session.get('username'):
            current_user = str(session.get('username')).strip()

        audit = AuditLog(
            action_type=action_type,
            username=current_user,
            target=target,
            details=details,
            ip_address=request.remote_addr or '127.0.0.1'
        )
        db.session.add(audit)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Audit log error: {e}")


@app.route('/')
def index():
    if 'user_id' in session:
        role_str = str(session.get('role', '')).lower()
        if 'admin' in role_str:
            return redirect(url_for('admin_dashboard'))
        elif 'head of institution' in role_str or 'head' in role_str or 'hoi' in role_str or 'principal' in role_str:
            return redirect(url_for('hoi_dashboard'))
        elif 'examination office' in role_str or 'exam' in role_str:
            return redirect(url_for('exam_office'))
        else:
            return redirect(url_for('ream_dashboard'))
    return redirect(url_for('login'))


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
            session.clear()  
            session['user_id'] = staff.id
            session['username'] = staff.username
            session['role'] = staff.role
            
            log_audit('USER_LOGIN', f'User {staff.username} logged in successfully as {staff.role}', target=staff.username)
            flash(f'Logged in successfully as {staff.role}', 'success')
            
            # Safe role checking
            role_str = str(staff.role).strip().lower()
            
            if 'admin' in role_str:
                return redirect(url_for('admin_dashboard'))
            elif any(x in role_str for x in ['head', 'hoi', 'principal', 'institution']):
                return redirect(url_for('hoi_dashboard'))
            elif any(x in role_str for x in ['exam', 'examination']):
                return redirect(url_for('exam_office'))
            else:
                return redirect(url_for('ream_dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')


@app.route('/logout')
def logout():
    if 'user_id' in session:
        username = session.get('username', 'User')
        log_audit('USER_LOGOUT', f'User {username} logged out.', target=username)
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

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
                log_audit('SET_ACTIVE_PERIOD', f'Locked active collection period to {active_term}, {active_year}', target='System Settings')
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
                    log_audit('ADD_FORM', f'Created new form/grade: {form_name}', target=form_name)
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
                log_audit('ADD_STREAM', f'Added stream {stream_name} to Form ID {form_id}', target=stream_name)
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
                log_audit('ENROLL_STUDENT', f'Enrolled student {full_name} ({adm_no}) in {form} {stream} for {year}', target=full_name)
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
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

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
    log_audit('PROMOTE_STUDENTS', f'Promoted {promoted_count} students from {source_year} to {target_year}', target=f'{source_year} to {target_year}')
    flash(f'Successfully promoted {promoted_count} students from {source_year} to {target_year}!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/upload_csv', methods=['POST'])
def upload_csv():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

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
            log_audit('CSV_UPLOAD', f'Bulk imported {success_count} students from CSV file ({file.filename})', target='Student Registry')
            flash(f'Successfully imported {success_count} students! ({duplicate_count} duplicates skipped).', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing CSV file: {str(e)}', 'danger')
    else:
        flash('Please upload a valid .csv file.', 'danger')

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    student = Student.query.get_or_404(student_id)
    student_name = student.full_name
    db.session.delete(student)
    db.session.commit()
    log_audit('DELETE_STUDENT', f'Deleted student record for {student_name} (Adm: {student.adm_no})', target=student_name)
    flash('Student record deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/download_template')
def download_template():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    csv_content = (
        'Admission Number,Full Name,Form/Grade,Stream,Gender,Term of Enrollment,Year\n'
    )
    csv_content += (
        'ADM001,John Doe,Form 1,East,Male,Term 1,2026\nADM002,Jane Smith,Form 1,West,Female,Term 2,2026\n'
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
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

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
                log_audit('CREATE_STAFF', f'Created staff account for username "{username}" with role "{role}"', target=username)
                flash('Staff account created successfully!', 'success')
                
        elif action in ['delete_staff', 'delete']:
            staff_id = request.form.get('staff_id')
            if staff_id:
                staff_member = StaffUser.query.get_or_404(staff_id)
                staff_username = staff_member.username
                db.session.delete(staff_member)
                db.session.commit()
                log_audit('DELETE_STAFF', f'Deleted staff account for username "{staff_username}"', target=staff_username)
                flash('Staff account deleted successfully.', 'success')

        elif action == 'reset_password':
            staff_id = request.form.get('staff_id')
            new_password = request.form.get('new_password')
            if staff_id and new_password:
                staff = StaffUser.query.get_or_404(staff_id)
                staff.password = new_password.strip()
                db.session.commit()
                log_audit('RESET_PASSWORD', f'Reset password for staff username "{staff.username}"', target=staff.username)
                flash(f'Password reset successfully!', 'success')
            
        return redirect(url_for('manage_staff'))

    staff_members = StaffUser.query.all()
    return render_template('manage_staff.html', staff_members=staff_members)


@app.route('/admin/staff/delete/<int:staff_id>', methods=['POST'])
def delete_staff(staff_id):
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    staff = StaffUser.query.get_or_404(staff_id)
    staff_username = staff.username
    db.session.delete(staff)
    db.session.commit()
    log_audit('DELETE_STAFF', f'Deleted staff account for username "{staff_username}"', target=staff_username)
    flash('Staff account deleted successfully.', 'success')
    return redirect(url_for('manage_staff'))

"""
@app.route('/portal/hoi', methods=['GET', 'POST'])
def hoi_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    # Safely fetch or auto-create global system settings
    setting = SystemSetting.query.first()
    if not setting:
        setting = SystemSetting(active_year='2026', active_term='Term 1')
        db.session.add(setting)
        db.session.commit()

    default_year = setting.active_year
    default_term = setting.active_term

    # Filter parameters from GET request
    selected_year = request.args.get('year', default_year)
    selected_term = request.args.get('term', default_term)
    selected_form = request.args.get('form', 'All')
    selected_stream = request.args.get('stream', 'All')
    selected_status = request.args.get('status', 'All')

    # 1. High-Level Metrics
    total_students = Student.query.filter_by(year=selected_year).count()
    
    total_reams_collected = db.session.query(db.func.sum(ReamRecord.reams_count)).scalar() or 0
    total_store_sheets = total_reams_collected * 500

    #total_sheets_requested = db.session.query(db.func.sum(ExamRequest.total_sheets_needed)).scalar() or 0
    #available_store_sheets = max(0, total_store_sheets - total_sheets_requested)
    total_sheets_requested = db.session.query(db.func.sum(ExamRequest.total_sheets_needed)).scalar() or 0
    remaining_sheets = max(0, total_store_sheets - total_sheets_requested)
    available_store_reams = remaining_sheets // 500

    total_loose_generated = db.session.query(db.func.sum(ExamRequest.loose_leftover_sheets)).scalar() or 0
    total_loose_disbursed = db.session.query(db.func.sum(SheetDisbursement.disbursed_sheets)).scalar() or 0
    active_loose_sheets = total_loose_generated - total_loose_disbursed

    # 2. School-wide Collection Rate Calculation for Active Term/Year
    term_records = ReamRecord.query.filter(
        db.func.lower(ReamRecord.term) == selected_term.lower(),
        ReamRecord.year == str(selected_year)
    ).all()
    
    submitted_student_ids = {r.student_id for r in term_records}
    total_submitted_count = len(submitted_student_ids)
    school_collection_percentage = round((total_submitted_count / total_students * 100), 1) if total_students > 0 else 0.0

    # 3. Form / Grade Analysis Data
    all_forms = db.session.query(Student.form.distinct()).filter_by(year=selected_year).all()
    form_list = [f[0] for f in all_forms if f[0]]
    form_analysis = []

    for f_name in sorted(form_list):
        f_students = Student.query.filter_by(year=selected_year, form=f_name).all()
        f_total = len(f_students)
        f_submitted = sum(1 for s in f_students if s.id in submitted_student_ids)
        f_pct = round((f_submitted / f_total * 100), 1) if f_total > 0 else 0.0
        form_analysis.append({
            'form': f_name,
            'total': f_total,
            'submitted': f_submitted,
            'percentage': f_pct
        })

    # 4. Stream Analysis Data
    stream_analysis = []
    streams_query = db.session.query(Student.form, Student.stream).filter_by(year=selected_year).distinct().all()
    unique_form_streams = sorted(list(set(streams_query)))

    for f_name, s_name in unique_form_streams:
        if not f_name or not s_name:
            continue
        fs_students = Student.query.filter_by(year=selected_year, form=f_name, stream=s_name).all()
        fs_total = len(fs_students)
        fs_submitted = sum(1 for s in fs_students if s.id in submitted_student_ids)
        fs_pct = round((fs_submitted / fs_total * 100), 1) if fs_total > 0 else 0.0
        stream_analysis.append({
            'form': f_name,
            'stream': s_name,
            'total': fs_total,
            'submitted': fs_submitted,
            'percentage': fs_pct
        })

    # 5. Filtered Student Report Query
    student_query = Student.query.filter_by(year=selected_year)
    if selected_form != 'All':
        student_query = student_query.filter_by(form=selected_form)
    if selected_stream != 'All':
        student_query = student_query.filter_by(stream=selected_stream)
    
    filtered_students_raw = student_query.order_by(Student.form, Student.stream, Student.adm_no).all()
    
    filtered_report_data = []
    for s in filtered_students_raw:
        is_submitted = s.id in submitted_student_ids
        status_str = 'Submitted' if is_submitted else 'Pending'
        
        if selected_status == 'Submitted' and not is_submitted:
            continue
        if selected_status == 'Pending' and is_submitted:
            continue
            
        filtered_report_data.append({
            'adm_no': s.adm_no,
            'full_name': s.full_name,
            'form': s.form,
            'stream': s.stream,
            'gender': s.gender,
            'status': status_str
        })
    year_results = db.session.query(Student.year.distinct()).all()
    available_years = sorted(list(set([y[0] for y in year_results]))) if year_results else ['2026']
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    disbursements = SheetDisbursement.query.order_by(SheetDisbursement.created_at.desc()).all()
    
    return render_template(
        'hoi_dashboard.html',
        role="Head of Institution",
        username=session.get('username'),
        selected_year=selected_year,
        selected_term=selected_term,
        selected_form=selected_form,
        selected_stream=selected_stream,
        selected_status=selected_status,
        available_years=available_years,
        total_students=total_students,
        total_reams_collected=total_reams_collected,
        #available_store_sheets=available_store_sheets,
        available_store_reams=available_store_reams,
        active_loose_sheets=active_loose_sheets,
        total_submitted_count=total_submitted_count,
        school_collection_percentage=school_collection_percentage,
        form_analysis=form_analysis,
        stream_analysis=stream_analysis,
        filtered_report_data=filtered_report_data,
        form_list=form_list,
        logs=logs,                      
        disbursements=disbursements
    )
"""
@app.route('/portal/hoi', methods=['GET', 'POST'])
def hoi_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    # Safely fetch or auto-create global system settings
    setting = SystemSetting.query.first()
    if not setting:
        setting = SystemSetting(active_year='2026', active_term='Term 1')
        db.session.add(setting)
        db.session.commit()

    default_year = setting.active_year
    default_term = setting.active_term

    # Filter parameters from GET request
    selected_year = request.args.get('year', default_year)
    selected_term = request.args.get('term', default_term)
    selected_form = request.args.get('form', 'All')
    selected_stream = request.args.get('stream', 'All')
    selected_status = request.args.get('status', 'All')

    # Term map for exemption calculations
    term_map = {'Term 1': 1, 'Term 2': 2, 'Term 3': 3}
    current_term_num = term_map.get(selected_term, 1)

    # Fetch all students for the selected year and classify active vs exempted
    all_year_students = Student.query.filter_by(year=selected_year).all()
    total_students = len(all_year_students)

    active_students = []
    exempted_count = 0
    exempted_student_ids = set()

    for s in all_year_students:
        s_term_num = term_map.get(s.enrollment_term, 1)
        if current_term_num < s_term_num:
            exempted_count += 1
            exempted_student_ids.add(s.id)
        else:
            active_students.append(s)

    # Expected reams count is strictly based on students active in or before this term
    expected_reams_count = len(active_students)

    # 2. School-wide Collection Rate Calculation for Active Term/Year (Moved up to calculate term collection first)
    term_records = ReamRecord.query.filter(
        db.func.lower(ReamRecord.term) == selected_term.lower(),
        ReamRecord.year == str(selected_year)
    ).all()
    
    submitted_student_ids = {r.student_id for r in term_records}
    total_submitted_count = len(submitted_student_ids)
    
    # Calculate reams collected strictly for this specific term and year
    total_reams_collected = sum(r.reams_count for r in term_records)

    # General store metrics (Physical store metrics remain cumulative across the year)
    all_year_reams_collected = db.session.query(db.func.sum(ReamRecord.reams_count)).scalar() or 0
    total_store_sheets = all_year_reams_collected * 500
    total_sheets_requested = db.session.query(db.func.sum(ExamRequest.total_sheets_needed)).scalar() or 0
    remaining_sheets = max(0, total_store_sheets - total_sheets_requested)
    available_store_reams = remaining_sheets // 500

    total_loose_generated = db.session.query(db.func.sum(ExamRequest.loose_leftover_sheets)).scalar() or 0
    total_loose_disbursed = db.session.query(db.func.sum(SheetDisbursement.disbursed_sheets)).scalar() or 0
    active_loose_sheets = total_loose_generated - total_loose_disbursed

    # Collection percentage based on expected (non-exempt) student pool
    school_collection_percentage = round((total_submitted_count / expected_reams_count * 100), 1) if expected_reams_count > 0 else 0.0

    # 3. Form / Grade Analysis Data (Exemptions respected)
    all_forms = db.session.query(Student.form.distinct()).filter_by(year=selected_year).all()
    form_list = [f[0] for f in all_forms if f[0]]
    form_analysis = []

    for f_name in sorted(form_list):
        f_students = [s for s in all_year_students if s.form == f_name]
        f_active = [s for s in f_students if s.id not in exempted_student_ids]
        f_total = len(f_active) # Denominator excludes exempt students
        f_submitted = sum(1 for s in f_active if s.id in submitted_student_ids)
        f_pct = round((f_submitted / f_total * 100), 1) if f_total > 0 else 0.0
        form_analysis.append({
            'form': f_name,
            'total': f_total,
            'submitted': f_submitted,
            'percentage': f_pct
        })

    # 4. Stream Analysis Data (Exemptions respected)
    stream_analysis = []
    streams_query = db.session.query(Student.form, Student.stream).filter_by(year=selected_year).distinct().all()
    unique_form_streams = sorted(list(set(streams_query)))

    for f_name, s_name in unique_form_streams:
        if not f_name or not s_name:
            continue
        fs_students = [s for s in all_year_students if s.form == f_name and s.stream == s_name]
        fs_active = [s for s in fs_students if s.id not in exempted_student_ids]
        fs_total = len(fs_active)
        fs_submitted = sum(1 for s in fs_active if s.id in submitted_student_ids)
        fs_pct = round((fs_submitted / fs_total * 100), 1) if fs_total > 0 else 0.0
        stream_analysis.append({
            'form': f_name,
            'stream': s_name,
            'total': fs_total,
            'submitted': fs_submitted,
            'percentage': fs_pct
        })

    # 5. Filtered Student Report Query
    student_query = Student.query.filter_by(year=selected_year)
    if selected_form != 'All':
        student_query = student_query.filter_by(form=selected_form)
    if selected_stream != 'All':
        student_query = student_query.filter_by(stream=selected_stream)
    
    filtered_students_raw = student_query.order_by(Student.form, Student.stream, Student.adm_no).all()
    
    filtered_report_data = []
    for s in filtered_students_raw:
        is_exempt = s.id in exempted_student_ids
        is_submitted = s.id in submitted_student_ids
        
        if is_exempt:
            status_str = 'Exempted'
        else:
            status_str = 'Submitted' if is_submitted else 'Pending'
        
        if selected_status == 'Submitted' and not is_submitted:
            continue
        if selected_status == 'Pending' and (is_submitted or is_exempt):
            continue
        if selected_status in ['Exempted', 'Exempt'] and not is_exempt:
            continue
            
        filtered_report_data.append({
            'adm_no': s.adm_no,
            'full_name': s.full_name,
            'form': s.form,
            'stream': s.stream,
            'gender': s.gender,
            'status': status_str
        })

    year_results = db.session.query(Student.year.distinct()).all()
    available_years = sorted(list(set([y[0] for y in year_results]))) if year_results else ['2026']
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    disbursements = SheetDisbursement.query.order_by(SheetDisbursement.created_at.desc()).all()
    
    return render_template(
        'hoi_dashboard.html',
        role="Head of Institution",
        username=session.get('username'),
        selected_year=selected_year,
        selected_term=selected_term,
        selected_form=selected_form,
        selected_stream=selected_stream,
        selected_status=selected_status,
        available_years=available_years,
        total_students=total_students,
        expected_reams_count=expected_reams_count,
        exempted_count=exempted_count,
        total_reams_collected=total_reams_collected,
        available_store_reams=available_store_reams,
        active_loose_sheets=active_loose_sheets,
        total_submitted_count=total_submitted_count,
        school_collection_percentage=school_collection_percentage,
        form_analysis=form_analysis,
        stream_analysis=stream_analysis,
        filtered_report_data=filtered_report_data,
        form_list=form_list,
        logs=logs,                    
        disbursements=disbursements
    )
"""
@app.route('/portal/hoi', methods=['GET', 'POST'])
def hoi_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    # Safely fetch or auto-create global system settings
    setting = SystemSetting.query.first()
    if not setting:
        setting = SystemSetting(active_year='2026', active_term='Term 1')
        db.session.add(setting)
        db.session.commit()

    default_year = setting.active_year
    default_term = setting.active_term

    # Filter parameters from GET request
    selected_year = request.args.get('year', default_year)
    selected_term = request.args.get('term', default_term)
    selected_form = request.args.get('form', 'All')
    selected_stream = request.args.get('stream', 'All')
    selected_status = request.args.get('status', 'All')

    # Term map for exemption calculations
    term_map = {'Term 1': 1, 'Term 2': 2, 'Term 3': 3}
    current_term_num = term_map.get(selected_term, 1)

    # Fetch all students for the selected year and classify active vs exempted
    all_year_students = Student.query.filter_by(year=selected_year).all()
    total_students = len(all_year_students)

    active_students = []
    exempted_count = 0
    exempted_student_ids = set()

    for s in all_year_students:
        s_term_num = term_map.get(s.enrollment_term, 1)
        if current_term_num < s_term_num:
            exempted_count += 1
            exempted_student_ids.add(s.id)
        else:
            active_students.append(s)

    # Expected reams count is strictly based on students active in or before this term
    expected_reams_count = len(active_students)

    # General store metrics
    total_reams_collected = db.session.query(db.func.sum(ReamRecord.reams_count)).scalar() or 0
    total_store_sheets = total_reams_collected * 500
    total_sheets_requested = db.session.query(db.func.sum(ExamRequest.total_sheets_needed)).scalar() or 0
    remaining_sheets = max(0, total_store_sheets - total_sheets_requested)
    available_store_reams = remaining_sheets // 500

    total_loose_generated = db.session.query(db.func.sum(ExamRequest.loose_leftover_sheets)).scalar() or 0
    total_loose_disbursed = db.session.query(db.func.sum(SheetDisbursement.disbursed_sheets)).scalar() or 0
    active_loose_sheets = total_loose_generated - total_loose_disbursed

    # 2. School-wide Collection Rate Calculation for Active Term/Year
    term_records = ReamRecord.query.filter(
        db.func.lower(ReamRecord.term) == selected_term.lower(),
        ReamRecord.year == str(selected_year)
    ).all()
    
    submitted_student_ids = {r.student_id for r in term_records}
    total_submitted_count = len(submitted_student_ids)
    
    # Collection percentage based on expected (non-exempt) student pool
    school_collection_percentage = round((total_submitted_count / expected_reams_count * 100), 1) if expected_reams_count > 0 else 0.0

    # 3. Form / Grade Analysis Data (Exemptions respected)
    all_forms = db.session.query(Student.form.distinct()).filter_by(year=selected_year).all()
    form_list = [f[0] for f in all_forms if f[0]]
    form_analysis = []

    for f_name in sorted(form_list):
        f_students = [s for s in all_year_students if s.form == f_name]
        f_active = [s for s in f_students if s.id not in exempted_student_ids]
        f_total = len(f_active) # Denominator excludes exempt students
        f_submitted = sum(1 for s in f_active if s.id in submitted_student_ids)
        f_pct = round((f_submitted / f_total * 100), 1) if f_total > 0 else 0.0
        form_analysis.append({
            'form': f_name,
            'total': f_total,
            'submitted': f_submitted,
            'percentage': f_pct
        })

    # 4. Stream Analysis Data (Exemptions respected)
    stream_analysis = []
    streams_query = db.session.query(Student.form, Student.stream).filter_by(year=selected_year).distinct().all()
    unique_form_streams = sorted(list(set(streams_query)))

    for f_name, s_name in unique_form_streams:
        if not f_name or not s_name:
            continue
        fs_students = [s for s in all_year_students if s.form == f_name and s.stream == s_name]
        fs_active = [s for s in fs_students if s.id not in exempted_student_ids]
        fs_total = len(fs_active)
        fs_submitted = sum(1 for s in fs_active if s.id in submitted_student_ids)
        fs_pct = round((fs_submitted / fs_total * 100), 1) if fs_total > 0 else 0.0
        stream_analysis.append({
            'form': f_name,
            'stream': s_name,
            'total': fs_total,
            'submitted': fs_submitted,
            'percentage': fs_pct
        })

    # 5. Filtered Student Report Query
    student_query = Student.query.filter_by(year=selected_year)
    if selected_form != 'All':
        student_query = student_query.filter_by(form=selected_form)
    if selected_stream != 'All':
        student_query = student_query.filter_by(stream=selected_stream)
    
    filtered_students_raw = student_query.order_by(Student.form, Student.stream, Student.adm_no).all()
    
    filtered_report_data = []
    for s in filtered_students_raw:
        is_exempt = s.id in exempted_student_ids
        is_submitted = s.id in submitted_student_ids
        
        if is_exempt:
            status_str = 'Exempted'
        else:
            status_str = 'Submitted' if is_submitted else 'Pending'
        
        if selected_status == 'Submitted' and not is_submitted:
            continue
        if selected_status == 'Pending' and (is_submitted or is_exempt):
            continue
        if selected_status == 'Exempted' and not is_exempt:
            continue
            
        filtered_report_data.append({
            'adm_no': s.adm_no,
            'full_name': s.full_name,
            'form': s.form,
            'stream': s.stream,
            'gender': s.gender,
            'status': status_str
        })

    year_results = db.session.query(Student.year.distinct()).all()
    available_years = sorted(list(set([y[0] for y in year_results]))) if year_results else ['2026']
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    disbursements = SheetDisbursement.query.order_by(SheetDisbursement.created_at.desc()).all()
    
    return render_template(
        'hoi_dashboard.html',
        role="Head of Institution",
        username=session.get('username'),
        selected_year=selected_year,
        selected_term=selected_term,
        selected_form=selected_form,
        selected_stream=selected_stream,
        selected_status=selected_status,
        available_years=available_years,
        total_students=total_students,
        expected_reams_count=expected_reams_count,
        exempted_count=exempted_count,
        total_reams_collected=total_reams_collected,
        available_store_reams=available_store_reams,
        active_loose_sheets=active_loose_sheets,
        total_submitted_count=total_submitted_count,
        school_collection_percentage=school_collection_percentage,
        form_analysis=form_analysis,
        stream_analysis=stream_analysis,
        filtered_report_data=filtered_report_data,
        form_list=form_list,
        logs=logs,                       
        disbursements=disbursements
    )
"""
"""
@app.route('/portal/ream', methods=['GET', 'POST'])
def ream_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

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
                        log_audit('REAM_COLLECTION', f"Marked ream submitted for student {student.full_name} ({selected_term}, {selected_year}).", target=student.full_name)
                        flash(f'Ream marked as submitted for {student.full_name}.', 'success')
                elif action == 'undo':
                    record = ReamRecord.query.filter_by(student_id=student_id, term=selected_term, year=selected_year).first()
                    if record:
                        db.session.delete(record)
                        db.session.commit()
                        log_audit('REAM_UNDO', f"Undid ream submission for student {student.full_name} ({selected_term}, {selected_year}).", target=student.full_name)
                        flash(f'Submission undone for {student.full_name}.', 'info')
                        
        return redirect(url_for('ream_dashboard', page=page))

    pagination = Student.query.filter_by(year=selected_year).order_by(Student.adm_no).paginate(page=page, per_page=15, error_out=False)
    students = pagination.items

    student_ids = [s.id for s in students]
    records = ReamRecord.query.filter(ReamRecord.student_id.in_(student_ids), ReamRecord.year==selected_year).all()
    
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

"""
@app.route('/portal/ream', methods=['GET', 'POST'])
def ream_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    setting = SystemSetting.query.first()
    selected_year = setting.active_year if setting else '2026'
    selected_term = setting.active_term if setting else 'Term 1'
    
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()
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
                        log_audit('REAM_COLLECTION', f"Marked ream submitted for student {student.full_name} ({selected_term}, {selected_year}).", target=student.full_name)
                        flash(f'Ream marked as submitted for {student.full_name}.', 'success')
                elif action == 'undo':
                    record = ReamRecord.query.filter_by(student_id=student_id, term=selected_term, year=selected_year).first()
                    if record:
                        db.session.delete(record)
                        db.session.commit()
                        log_audit('REAM_UNDO', f"Undid ream submission for student {student.full_name} ({selected_term}, {selected_year}).", target=student.full_name)
                        flash(f'Submission undone for {student.full_name}.', 'info')
                        
        return redirect(url_for('ream_dashboard', page=page, search=search_query))

    student_query = Student.query.filter_by(year=selected_year)
    if search_query:
        student_query = student_query.filter(
            db.or_(
                Student.adm_no.ilike(f"%{search_query}%"),
                Student.full_name.ilike(f"%{search_query}%")
            )
        )

    pagination = student_query.order_by(Student.adm_no).paginate(page=page, per_page=15, error_out=False)
    students = pagination.items

    student_ids = [s.id for s in students]
    records = ReamRecord.query.filter(ReamRecord.student_id.in_(student_ids), ReamRecord.year==selected_year).all() if student_ids else []
    
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
        selected_term=selected_term,
        search_query=search_query
    )

@app.route('/portal/exam')
def exam_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))
    return redirect(url_for('exam_office'))
"""
@app.route('/examination-office', methods=['GET', 'POST'])
def exam_office():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    total_reams_collected = db.session.query(db.func.sum(ReamRecord.reams_count)).scalar() or 0
    total_store_sheets = total_reams_collected * 500
    total_sheets_requested = db.session.query(db.func.sum(ExamRequest.total_sheets_needed)).scalar() or 0
    available_store_sheets = max(0, total_store_sheets - total_sheets_requested)

    total_loose_generated = db.session.query(db.func.sum(ExamRequest.loose_leftover_sheets)).scalar() or 0
    total_loose_disbursed = db.session.query(db.func.sum(SheetDisbursement.disbursed_sheets)).scalar() or 0
    active_loose_sheets = total_loose_generated - total_loose_disbursed

    if request.method == 'POST':
        action = request.form.get('action')

        if total_reams_collected <= 0:
            flash("STORE STATUS ERROR: NO REAM COLLECTED YET. Please wait for collection desk.", "error")
            return redirect(url_for('exam_office'))

        # === HANDLER 1: REQUEST REAMS ===
        if action == 'request_reams':
            if active_loose_sheets > 20:
                flash("REQUEST DENIED: ACTIVE LOOSE LEFTOVER SHEETS EXCEED 20. You must disburse loose sheets first.", "error")
                return redirect(url_for('exam_office'))

            subject = request.form.get('subject')
            purpose = request.form.get('purpose')
            target_form = request.form.get('target_form')
            stream = request.form.get('stream')
            num_students = int(request.form.get('num_students'))
            sheets_per_student = int(request.form.get('sheets_per_student'))

            raw_needed = num_students * sheets_per_student
            padding = 60 if raw_needed <= 250 else 50
            total_needed_with_padding = raw_needed + padding

            if total_needed_with_padding > available_store_sheets:
                flash("REQUESTING MORE THAN IS AVAILABLE IN THE STORE.", "error")
                return redirect(url_for('exam_office'))

            reams_to_take = math.ceil(total_needed_with_padding / 500)
            loose_leftover = (reams_to_take * 500) - total_needed_with_padding

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
                reams_allocated=reams_to_take
            )
            db.session.add(new_req)
            db.session.commit()
            log_audit('EXAM_REQUEST', f'Requested {total_needed_with_padding} sheets for exam: {subject} ({target_form} {stream})', target=subject)
            flash("Exam ream request successfully submitted.", "success")
            return redirect(url_for('exam_office'))

        # === HANDLER 2: DISBURSE LOOSE SHEETS ===
        if action == 'disburse_sheets':
            subject = request.form.get('subject')
            purpose = request.form.get('purpose')
            target_form = request.form.get('target_form')
            stream = request.form.get('stream')
            num_students = int(request.form.get('num_students'))
            sheets_per_student = int(request.form.get('sheets_per_student'))
            disbursed_count = num_students * sheets_per_student

            if disbursed_count > active_loose_sheets:
                flash("ERROR: CANNOT DISBURSE MORE THAN AVAILABLE ACTIVE LOOSE SHEETS.", "error")
                return redirect(url_for('exam_office'))

            new_disbursement = SheetDisbursement(
                subject=subject,
                purpose=purpose,
                target_form=target_form,
                stream=stream,
                num_students=num_students,
                sheets_per_student=sheets_per_student,
                disbursed_sheets=disbursed_count
            )
            db.session.add(new_disbursement)
            db.session.commit()
            log_audit('LOOSE_DISBURSEMENT', f'Disbursed {disbursed_count} loose sheets for: {subject} ({target_form} {stream})', target=subject)
            flash("Loose sheets successfully disbursed.", "success")
            return redirect(url_for('exam_office'))

    exam_requests = ExamRequest.query.order_by(ExamRequest.id.desc()).all()
    
    disbursements = SheetDisbursement.query.order_by(SheetDisbursement.id.desc()).all()

    return render_template(
        'examination_office.html',
        role="Examination Office",
        username=session.get('username'),
        total_store_sheets=available_store_sheets,
        available_store_sheets=available_store_sheets,
        active_loose_sheets=active_loose_sheets,
        exam_requests=exam_requests,
        disbursements=disbursements
    )
"""
@app.route('/examination-office', methods=['GET', 'POST'])
def exam_office():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    total_reams_collected = db.session.query(db.func.sum(ReamRecord.reams_count)).scalar() or 0
    total_store_sheets = total_reams_collected * 500
    total_sheets_requested = db.session.query(db.func.sum(ExamRequest.total_sheets_needed)).scalar() or 0
    available_store_sheets = max(0, total_store_sheets - total_sheets_requested)

    total_loose_generated = db.session.query(db.func.sum(ExamRequest.loose_leftover_sheets)).scalar() or 0
    total_loose_disbursed = db.session.query(db.func.sum(SheetDisbursement.disbursed_sheets)).scalar() or 0
    active_loose_sheets = total_loose_generated - total_loose_disbursed

    if request.method == 'POST':
        action = request.form.get('action')

        if total_reams_collected <= 0:
            flash("STORE STATUS ERROR: NO REAM COLLECTED YET. Please wait for collection desk.", "error")
            return redirect(url_for('exam_office'))

        # === HANDLER 1: REQUEST REAMS ===
        if action == 'request_reams':
            if active_loose_sheets > 20:
                flash("REQUEST DENIED: ACTIVE LOOSE LEFTOVER SHEETS EXCEED 20. You must disburse loose sheets first.", "error")
                return redirect(url_for('exam_office'))

            subject = request.form.get('subject')
            purpose = request.form.get('purpose')
            target_form = request.form.get('target_form')
            stream = request.form.get('stream')
            num_students = int(request.form.get('num_students'))
            sheets_per_student = int(request.form.get('sheets_per_student'))

            raw_needed = num_students * sheets_per_student
            padding = 60 if raw_needed <= 250 else 50
            total_needed_with_padding = raw_needed + padding

            if total_needed_with_padding > available_store_sheets:
                flash("REQUESTING MORE THAN IS AVAILABLE IN THE STORE.", "error")
                return redirect(url_for('exam_office'))

            reams_to_take = math.ceil(total_needed_with_padding / 500)
            loose_leftover = (reams_to_take * 500) - total_needed_with_padding

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
                reams_allocated=reams_to_take
            )
            db.session.add(new_req)
            db.session.commit()
            
            # --- SMS NOTIFICATION TRIGGER FOR HOI ---
            current_remaining_reams = (available_store_sheets - total_needed_with_padding) // 500
            sms_text = (
               "📊 *REAMPULSE AUDIT UPDATE* 📊\n"
               "-----------------------------------\n"
               f"🟢 *New Print Run:* {subject} ({target_form} {stream})\n"
               "───────────────────────────────────\n"
               f"📦 *Store Left:* {current_remaining_reams} Reams\n"
               "───────────────────────────────────\n"
               f"📋 *Reams Taken:* {reams_to_take} Reams ({total_needed_with_padding} sheets)\n"
               "-----------------------------------\n"
               "*(System Generated Notification)*"
            )
            send_hoi_sms(sms_text)
            # ----------------------------------------

            log_audit('EXAM_REQUEST', f'Requested {total_needed_with_padding} sheets for exam: {subject} ({target_form} {stream})', target=subject)
            flash("Exam ream request successfully submitted.", "success")
            return redirect(url_for('exam_office'))

        # === HANDLER 2: DISBURSE LOOSE SHEETS ===
        if action == 'disburse_sheets':
            subject = request.form.get('subject')
            purpose = request.form.get('purpose')
            target_form = request.form.get('target_form')
            stream = request.form.get('stream')
            num_students = int(request.form.get('num_students'))
            sheets_per_student = int(request.form.get('sheets_per_student'))
            disbursed_count = num_students * sheets_per_student

            if disbursed_count > active_loose_sheets:
                flash("ERROR: CANNOT DISBURSE MORE THAN AVAILABLE ACTIVE LOOSE SHEETS.", "error")
                return redirect(url_for('exam_office'))

            new_disbursement = SheetDisbursement(
                subject=subject,
                purpose=purpose,
                target_form=target_form,
                stream=stream,
                num_students=num_students,
                sheets_per_student=sheets_per_student,
                disbursed_sheets=disbursed_count
            )
            db.session.add(new_disbursement)
            db.session.commit()
            log_audit('LOOSE_DISBURSEMENT', f'Disbursed {disbursed_count} loose sheets for: {subject} ({target_form} {stream})', target=subject)
            flash("Loose sheets successfully disbursed.", "success")
            return redirect(url_for('exam_office'))

    exam_requests = ExamRequest.query.order_by(ExamRequest.id.desc()).all()
    disbursements = SheetDisbursement.query.order_by(SheetDisbursement.id.desc()).all()

    return render_template(
        'examination_office.html',
        role="Examination Office",
        username=session.get('username'),
        total_store_sheets=available_store_sheets,
        available_store_sheets=available_store_sheets,
        active_loose_sheets=active_loose_sheets,
        exam_requests=exam_requests,
        disbursements=disbursements
    )
@app.route('/admin/audit-logs')
def audit_logs():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))
        
    # Fetch filter parameters from GET request
    selected_action = request.args.get('action', 'All')
    selected_user = request.args.get('user', 'All')
    page = request.args.get('page', 1, type=int)
    
    # Base query for audit logs
    query = AuditLog.query
    
    if selected_action != 'All':
        query = query.filter_by(action_type=selected_action)
    if selected_user != 'All':
        query = query.filter_by(username=selected_user)
        
    # Pagination for logs
    pagination = query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=15, error_out=False)
    logs = pagination.items
    
    # Fetch distinct action types and usernames for dropdown filters
    actions = [row[0] for row in db.session.query(AuditLog.action_type.distinct()).all() if row[0]]
    usernames = [row[0] for row in db.session.query(AuditLog.username.distinct()).all() if row[0]]
    
    # Fetch sheet disbursements history
    disbursements = SheetDisbursement.query.order_by(SheetDisbursement.created_at.desc()).all()
    
    return render_template(
        'audit_logs.html',
        username=session.get('username'),
        logs=logs,
        pagination=pagination,
        actions=actions,
        usernames=usernames,
        selected_action=selected_action,
        selected_user=selected_user,
        disbursements=disbursements
    )

#@app.route('/admin/audit-logs')
#def audit_logs():
   # if 'user_id' not in session:
       # flash('Please log in first.', 'warning')
       # return redirect(url_for('login'))
        
   # logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(200).all()
   # return render_template('audit_logs.html', audit_logs=logs)

import africastalking

def send_hoi_sms(message_body):
    # Hardcoded directly to bypass Render environment variable lag
    username = 'almeric'
    api_key = 'atsk_4ee05808b1af7571784ad8c9d6fd6a5cb690ad6885f9e148575ab7c07ac6ac9ae24daf5d'
    hoi_phone = '+254755479890'
    
    print(f"DEBUG: Attempting to send SMS to {hoi_phone} using user {username}")

    africastalking.initialize(username, api_key)
    sms = africastalking.SMS

    try:
        response = sms.send(message_body, [hoi_phone])
        print("SMS sent successfully:", response)
    except Exception as e:
        print(f"FAILED TO SEND SMS EXCEPTION: {e}")

@app.route('/hoi/download-report-csv')
def download_filtered_report_csv():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))
        
    # Grab the filter parameters from the request
    selected_year = request.args.get('year')
    selected_term = request.args.get('term')
    selected_form = request.args.get('form', 'All')
    selected_stream = request.args.get('stream', 'All')
    selected_status = request.args.get('status', 'All')
    
    # Filter the student records based on the selection
    query = StudentRecord.query
    if selected_year:
        query = query.filter_by(year=selected_year)
    if selected_term:
        query = query.filter_by(term=selected_term)
    if selected_form != 'All':
        query = query.filter_by(form=selected_form)
    if selected_stream != 'All':
        query = query.filter_by(stream=selected_stream)
    if selected_status != 'All':
        query = query.filter_by(status=selected_status)
        
    filtered_records = query.all()

    # Build the CSV file rows
    output = []
    output.append(['Adm No', 'Full Name', 'Form / Grade', 'Stream', 'Gender', 'Status', 'Year', 'Term'])
    
    for row in filtered_records:
        output.append([
            str(row.adm_no),
            str(row.full_name),
            str(row.form),
            str(row.stream),
            str(row.gender),
            str(row.status),
            str(selected_year or ''),
            str(selected_term or '')
        ])

    response = make_response('\n'.join([','.join([f'"{str(cell)}"' for cell in row]) for row in output]))
    response.headers["Content-Disposition"] = f"attachment; filename=reampulse_report_{selected_term}_{selected_year}.csv"
    response.headers["Content-type"] = "text/csv"
    return response

if __name__ == '__main__':
    app.run(debug=True)