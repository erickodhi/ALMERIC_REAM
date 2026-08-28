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
    # ... your existing POST handling code (add_form, add_stream, etc.) ...

    # Explicitly query forms and attach their streams as a clean list of dictionaries or names
    forms_list = []
    for f in Form.query.all():
        # Get all streams associated with this form
        form_streams = Stream.query.filter_by(form_id=f.id).all()
        forms_list.append({
            'id': f.id,
            'name': f.name,
            'streams': [{'name': s.name if hasattr(s, 'name') else s.stream_name} for s in form_streams]
        })

    students = Student.query.all()
    return render_template('admin.html', forms=forms_list, students=students)


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