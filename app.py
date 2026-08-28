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
      if form_name and not Form.query.filter_by(name=form_name).first():
        db.session.add(Form(name=form_name))
        db.session.commit()
        flash(f'Form {form_name} created successfully!', 'success')
      else:
        flash('Form name already exists or is empty.', 'danger')

    elif action == 'add_stream':
      stream_name = request.form.get('stream_name')
      form_id = request.form.get('form_id')
      if stream_name and form_id:
        db.session.add(Stream(name=stream_name, form_id=form_id))
        db.session.commit()
        flash(f'Stream {stream_name} added successfully!', 'success')

    elif action == 'enroll_student':
      adm_no = request.form.get('adm_no')
      full_name = request.form.get('full_name')
      form = request.form.get('form')
      stream = request.form.get('stream')
      gender = request.form.get('gender')
      enrollment_term = request.form.get('enrollment_term')
      year = request.form.get('year', '2026')

      if adm_no and not Student.query.filter_by(adm_no=adm_no).first():
        new_student = Student(
            adm_no=adm_no,
            full_name=full_name,
            form=form,
            stream=stream,
            gender=gender,
            enrollment_term=enrollment_term,
            year=year,
        )
        db.session.add(new_student)
        db.session.commit()
        flash(f'Student {full_name} enrolled successfully!', 'success')
      else:
        flash(
            'Admission number already exists or is invalid.',
            'danger',
        )

    return redirect(url_for('admin_dashboard'))

  forms = Form.query.all()
  streams = Stream.query.all()
  students = Student.query.all()
  return render_template(
      'admin.html', forms=forms, streams=streams, students=students
  )


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


@app.route('/')
def index():
  return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
  app.run(debug=True)