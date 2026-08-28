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
    # ... your existing POST handling logic (add_form, add_stream, enroll_student, etc.) ...

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


@app.route('/')
def index():
  return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
  app.run(debug=True)