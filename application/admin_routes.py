from flask import render_template, request, redirect, url_for, session, flash, Blueprint
import pyodbc
from email_service import email_service
import bcrypt 

# Create a Blueprint
admin_bp = Blueprint('admin_routes', __name__, url_prefix='/admin')

# registration function for admin routes
def register_admin_routes(app, get_db_connection, admin_required, validate_student_id):

    @admin_bp.route('/')
    @admin_required
    def admin_dashboard():
        conn = get_db_connection()
        if not conn:
            flash('Database connection error. Please try again.', 'error')
            return redirect(url_for('misc_routes.logout'))
        
        try:
            cursor = conn.cursor()
        
            # Get all CCAs
            cursor.execute("SELECT CCAId, Name, Description FROM CCA ORDER BY Name")
            all_ccas = cursor.fetchall()
            
            # Get all students
            cursor.execute("SELECT StudentId, Name, Email FROM Student ORDER BY Name")
            all_students = cursor.fetchall()
            
            # Get CCA memberships with details
            membership_query = """
            SELECT s.Name as StudentName, c.Name as CCAName, cm.CCARole, 
                   s.StudentId, c.CCAId, cm.MemberId
            FROM CCAMembers cm
            INNER JOIN Student s ON cm.UserId IN (
                SELECT UserId FROM UserDetails WHERE StudentId = s.StudentId
            )
            INNER JOIN CCA c ON cm.CCAId = c.CCAId
            ORDER BY c.Name, s.Name
            """
            cursor.execute(membership_query)
            memberships = cursor.fetchall()
            
            return render_template('admin_dashboard.html',
                                 ccas=all_ccas,
                                 students=all_students,
                                 memberships=memberships,
                                 user_name=session['name'])
            
        except Exception as e:
            print(f"Admin dashboard error: {e}")
            flash('Error loading admin dashboard.', 'error')
            return render_template('admin_dashboard.html', 
                                 ccas=[], students=[], memberships=[],
                                 user_name=session['name'])
        finally:
            if conn:
                conn.close()

    @admin_bp.route('/create-student', methods=['GET', 'POST'])
    @admin_required
    def create_student():
        if request.method == 'POST':
            student_id = request.form.get('student_id', '').strip()
            password = request.form.get('password', '').strip()
            
            # Basic validation
            if not student_id or not password:
                flash('Both Student ID and password are required.', 'error')
                return render_template('create_student.html')
            
            if not validate_student_id(student_id):
                flash('Student ID must be 7 digits.', 'error')
                return render_template('create_student.html')
            
            conn = get_db_connection()
            if not conn:
                flash('Database connection error.', 'error')
                return render_template('create_student.html')
            
            try:
                cursor = conn.cursor()
                
                # Check if student exists 
                cursor.execute("SELECT StudentId, Name, Email FROM Student WHERE StudentId = ?", (int(student_id),))
                student_record = cursor.fetchone()
                
                if not student_record:
                    flash(f'Student ID {student_id} not found in student records. Please contact administration to add student to system first.', 'error')
                    return render_template('create_student.html')
                
                # Check if student already has a registered account 
                cursor.execute("SELECT UserId FROM UserDetails WHERE StudentId = ?", (int(student_id),))
                existing_account = cursor.fetchone()
                
                if existing_account:
                    flash(f'Student {student_record[1]} (ID: {student_id}) already has a login account.', 'error')
                    return render_template('create_student.html')
                
                # Mark password as temporary 
                temp_password = f"TEMP_{password}"
                cursor.execute("""
                    INSERT INTO UserDetails (Username, StudentId, Password, SystemRole)
                    VALUES (?, ?, ?, 'student')
                """, (int(student_id), int(student_id), temp_password))
                
                conn.commit()
                
                # Send email to reset password after successful account creation
                student_name = student_record[1]
                student_email = student_record[2]
                
                base_message = f'Login account created successfully for {student_name} (ID: {student_id})!'
                
                if student_email:
                    try:
                        email_sent = email_service.send_student_credentials(
                            student_name=student_name,
                            student_email=student_email,
                            student_id=student_id,
                            temp_password=password
                        )
                        
                        if email_sent:
                            flash(f'{base_message} Email with login credentials sent to {student_email}.', 'success')
                        else:
                            flash(f'{base_message} However, email notification failed. Please provide credentials manually.', 'warning')
                    except Exception as e:
                        print(f"Email sending error: {e}")
                        flash(f'{base_message} However, email notification failed. Please provide credentials manually.', 'warning')
                else:
                    flash(f'{base_message} No email on file - please provide credentials manually.', 'warning')
                
                return redirect(url_for('admin_routes.admin_dashboard'))
                
            except Exception as e:
                conn.rollback()
                print(f"Create student account error: {e}")
                flash('Error creating student account. Please try again.', 'error')
                return render_template('create_student.html')
            finally:
                if conn:
                    conn.close()
        
        return render_template('create_student.html')

    @admin_bp.route('/create-cca', methods=['GET', 'POST'])
    @admin_required
    def create_cca():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('CCA name is required.', 'error')
                return render_template('create_cca.html')
            
            conn = get_db_connection()
            if not conn:
                flash('Database connection error.', 'error')
                return render_template('create_cca.html')
            
            try:
                cursor = conn.cursor()
                
                # Check if CCA name already exists
                cursor.execute("SELECT CCAId FROM CCA WHERE Name = ?", (name,))
                if cursor.fetchone():
                    flash('CCA name already exists.', 'error')
                    return render_template('create_cca.html')
                
                # Insert new CCA
                cursor.execute("""
                    INSERT INTO CCA (Name, Description)
                    VALUES (?, ?)
                """, (name, description or ''))
                
                conn.commit()
                flash(f'CCA "{name}" created successfully!', 'success')
                return redirect(url_for('admin_routes.admin_dashboard'))
                
            except Exception as e:
                conn.rollback()
                print(f"Create CCA error: {e}")
                flash('Error creating CCA. Please try again.', 'error')
                return render_template('create_cca.html')
            finally:
                if conn:
                    conn.close()
        
        return render_template('create_cca.html')

    @admin_bp.route('/cca/<int:cca_id>')
    @admin_required
    def view_cca(cca_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('admin_routes.admin_dashboard'))
        
        try:
            cursor = conn.cursor()
            
            # Get CCA details
            cursor.execute("SELECT CCAId, Name, Description FROM CCA WHERE CCAId = ?", (cca_id,))
            cca = cursor.fetchone()
            
            if not cca:
                flash('CCA not found.', 'error')
                return redirect(url_for('admin_routes.admin_dashboard'))
            
            # Get CCA members
            members_query = """
            SELECT s.StudentId, s.Name, s.Email, cm.CCARole, cm.MemberId, ud.UserId
            FROM CCAMembers cm
            INNER JOIN UserDetails ud ON cm.UserId = ud.UserId
            INNER JOIN Student s ON ud.StudentId = s.StudentId
            WHERE cm.CCAId = ?
            ORDER BY s.Name
            """
            cursor.execute(members_query, (cca_id,))
            members = cursor.fetchall()
            
            # Get all students not in this CCA (for assignment)
            not_in_cca_query = """
            SELECT s.StudentId, s.Name
            FROM Student s
            INNER JOIN UserDetails ud ON s.StudentId = ud.StudentId
            WHERE ud.UserId NOT IN (
                SELECT UserId FROM CCAMembers WHERE CCAId = ?
            )
            ORDER BY s.Name
            """
            cursor.execute(not_in_cca_query, (cca_id,))
            available_students = cursor.fetchall()
            
            return render_template('view_cca.html', 
                                 cca=cca, 
                                 members=members, 
                                 available_students=available_students)
            
        except Exception as e:
            print(f"View CCA error: {e}")
            flash('Error loading CCA details.', 'error')
            return redirect(url_for('admin_routes.admin_dashboard'))
        finally:
            if conn:
                conn.close()

    @admin_bp.route('/cca/<int:cca_id>/edit', methods=['POST'])
    @admin_required
    def edit_cca(cca_id):
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash('CCA name is required.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        
        try:
            cursor = conn.cursor()
            
            # Check if new name conflicts with existing CCAs (excluding current one)
            cursor.execute("SELECT CCAId FROM CCA WHERE Name = ? AND CCAId != ?", (name, cca_id))
            if cursor.fetchone():
                flash('CCA name already exists.', 'error')
                return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
            # Update CCA
            cursor.execute("""
                UPDATE CCA 
                SET Name = ?, Description = ?
                WHERE CCAId = ?
            """, (name, description, cca_id))
            
            conn.commit()
            flash('CCA updated successfully!', 'success')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
        except Exception as e:
            conn.rollback()
            print(f"Edit CCA error: {e}")
            flash('Error updating CCA.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        finally:
            if conn:
                conn.close()

    @admin_bp.route('/cca/<int:cca_id>/add-student', methods=['POST'])
    @admin_required
    def add_student_to_cca(cca_id):
        student_id = request.form.get('student_id')
        role = request.form.get('role')
        
        if not all([student_id, role]):
            flash('Please select both student and role.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        
        try:
            cursor = conn.cursor()
            
            cursor.execute("SELECT UserId FROM UserDetails WHERE StudentId = ?", (int(student_id),))
            user_result = cursor.fetchone()
            if not user_result:
                flash('Student not found.', 'error')
                return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
            user_id = user_result[0]
            
            cursor.execute("""
                INSERT INTO CCAMembers (UserId, CCAId, CCARole)
                VALUES (?, ?, ?)
            """, (user_id, cca_id, role))
            
            conn.commit()
            flash('Student added to CCA successfully!', 'success')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
        except Exception as e:
            conn.rollback()
            print(f"Add student to CCA error: {e}")
            flash('Error adding student to CCA.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        finally:
            if conn:
                conn.close()

    @admin_bp.route('/cca/<int:cca_id>/remove-student/<int:member_id>', methods=['POST'])
    @admin_required
    def remove_student_from_cca(cca_id, member_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM CCAMembers WHERE MemberId = ? AND CCAId = ?", (member_id, cca_id))
            conn.commit()
            flash('Student removed from CCA successfully!', 'success')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
        except Exception as e:
            conn.rollback()
            print(f"Remove student from CCA error: {e}")
            flash('Error removing student from CCA.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        finally:
            if conn:
                conn.close()

    @admin_bp.route('/cca/<int:cca_id>/delete', methods=['POST'])
    @admin_required
    def delete_cca(cca_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('admin_routes.admin_dashboard'))
        
        try:
            cursor = conn.cursor()
            
            cursor.execute("SELECT Name FROM CCA WHERE CCAId = ?", (cca_id,))
            cca_result = cursor.fetchone()
            if not cca_result:
                flash('CCA not found.', 'error')
                return redirect(url_for('admin_routes.admin_dashboard'))
            
            cca_name = cca_result[0]
            
            cursor.execute("DELETE FROM CCAMembers WHERE CCAId = ?", (cca_id,))
            cursor.execute("DELETE FROM Votes WHERE PollId IN (SELECT PollId FROM Poll WHERE CCAId = ?)", (cca_id,))
            cursor.execute("DELETE FROM Options WHERE PollId IN (SELECT PollId FROM Poll WHERE CCAId = ?)", (cca_id,))
            cursor.execute("DELETE FROM Poll WHERE CCAId = ?", (cca_id,))
            cursor.execute("DELETE FROM CCA WHERE CCAId = ?", (cca_id,))
            
            conn.commit()
            flash(f'CCA "{cca_name}" and all related data deleted successfully!', 'success')
            return redirect(url_for('admin_routes.admin_dashboard'))
            
        except Exception as e:
            conn.rollback()
            print(f"Delete CCA error: {e}")
            flash('Error deleting CCA.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        finally:
            if conn:
                conn.close()
    
    @admin_bp.route('/api/search-students')
    @admin_required
    def search_students():
        """API endpoint to search for students by name or student ID"""
        search_query = request.args.get('q', '').strip()
        cca_id = request.args.get('cca_id', '')
        
        if not search_query or len(search_query) < 2:
            return {'students': []}
        
        conn = get_db_connection()
        if not conn:
            return {'error': 'Database connection error'}, 500
        
        try:
            cursor = conn.cursor()
            
            search_sql = """
            SELECT s.StudentId, s.Name, s.Email
            FROM Student s
            INNER JOIN UserDetails ud ON s.StudentId = ud.StudentId
            WHERE (s.Name LIKE ? OR CAST(s.StudentId AS VARCHAR) LIKE ?)
            AND ud.UserId NOT IN (
                SELECT UserId FROM CCAMembers WHERE CCAId = ?
            )
            ORDER BY s.Name
            """
            
            search_pattern = f'%{search_query}%'
            cursor.execute(search_sql, (search_pattern, search_pattern, cca_id))
            students = cursor.fetchall()
            
            result = []
            for student in students:
                result.append({
                    'student_id': student[0],
                    'name': student[1],
                    'email': student[2]
                })
            
            return {'students': result}
            
        except Exception as e:
            print(f"Search students error: {e}")
            return {'error': 'Search failed'}, 500
        finally:
            if conn:
                conn.close()

    @admin_bp.route('/cca/<int:cca_id>/add-multiple-students', methods=['POST'])
    @admin_required
    def add_multiple_students_to_cca(cca_id):
        """Add multiple students to a CCA in a single operation"""
        student_ids = request.form.getlist('student_ids[]')
        role = request.form.get('role', 'member')
        
        if not student_ids:
            flash('Please select at least one student.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        
        try:
            cursor = conn.cursor()
            
            placeholders = ','.join(['?' for _ in student_ids])
            cursor.execute(f"""
                SELECT ud.UserId, s.StudentId, s.Name 
                FROM UserDetails ud
                INNER JOIN Student s ON ud.StudentId = s.StudentId
                WHERE s.StudentId IN ({placeholders})
            """, student_ids)
            
            user_data = cursor.fetchall()
            
            membership_data = [(user[0], cca_id, role) for user in user_data]
            cursor.executemany("""
                INSERT INTO CCAMembers (UserId, CCAId, CCARole)
                VALUES (?, ?, ?)
            """, membership_data)
            
            conn.commit()
            
            added_count = len(user_data)
            flash(f'{added_count} students have been added to the CCA as {role}s!', 'success')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Add multiple students error: {e}")
            flash('Error adding students to CCA. Please try again.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        finally:
            if conn:
                conn.close()

    # Register the blueprint with the app
    app.register_blueprint(admin_bp)
