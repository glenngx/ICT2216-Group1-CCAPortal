from flask import render_template, request, redirect, url_for, session, flash, Blueprint
from email_service import email_service
import bcrypt
from application.auth_utils import admin_required
from .models import db, CCA, Student, CCAMembers, User, Poll, PollOption, PollVote, LoginLog, AdminLog
from application.auth_utils import log_admin_action

# Create a Blueprint
admin_bp = Blueprint('admin_routes', __name__, url_prefix='/admin')

# registration function for admin routes
def register_admin_routes(app, get_db_connection, validate_student_id):

    @admin_bp.route('/')
    @admin_required
    def admin_dashboard():
        try:
            # Get all CCAs
            #SQL refactoring
            # cursor.execute("SELECT CCAId, Name, Description FROM CCA ORDER BY Name")
            # all_ccas = cursor.fetchall()
            all_ccas = CCA.query.order_by(CCA.Name).all()
            # Retrieves all CCAs, ordered by name.

            # Get all students
            #SQL refactoring
            # cursor.execute("SELECT StudentId, Name, Email FROM v_ActiveStudents ORDER BY Name")
            # all_students = cursor.fetchall()
            all_students = Student.query.order_by(Student.Name).all()
            # Retrieves all students, ordered by name.
            
            # Get CCA memberships with details
            #SQL refactoring
            # membership_query = """
            # SELECT s.Name as StudentName, c.Name as CCAName, cm.CCARole, 
            #     s.StudentId, c.CCAId, cm.MemberId
            # FROM CCAMembers cm
            # INNER JOIN Student s ON cm.UserId IN (
            #     SELECT UserId FROM UserDetails WHERE StudentId = s.StudentId
            # )
            # INNER JOIN CCA c ON cm.CCAId = c.CCAId
            # ORDER BY c.Name, s.Name
            # """
            # cursor.execute(membership_query)
            # memberships = cursor.fetchall()
            memberships = db.session.query(
                Student.Name.label('StudentName'),
                CCA.Name.label('CCAName'),
                CCAMembers.CCARole,
                Student.StudentId,
                CCA.CCAId,
                CCAMembers.MemberId
            ).join(User, CCAMembers.UserId == User.UserId).join(Student).join(CCA).order_by(CCA.Name, Student.Name).all()
            # Joins CCA, CCAMembers, User, and Student to retrieve membership details.

            # Get students who need password setup (Password is NULL)
            #SQL refactoring
            # password_setup_query = """
            # SELECT s.StudentId, s.Name, s.Email
            # FROM Student s
            # INNER JOIN UserDetails ud ON s.StudentId = ud.StudentId
            # WHERE ud.Password IS NULL
            # ORDER BY s.Name
            # """
            # cursor.execute(password_setup_query)
            # students_needing_password_setup = cursor.fetchall()
            students_needing_password_setup = db.session.query(
                Student.StudentId, Student.Name, Student.Email
            ).join(User).filter(User.Password == None).order_by(Student.Name).all()
            # Finds students with NULL passwords, indicating they need to set it up.
            
            return render_template('admin_dashboard.html',
                                ccas=all_ccas,
                                students=all_students,
                                memberships=memberships,
                                students_needing_password_setup=students_needing_password_setup,
                                user_name=session['name'])
            
        except Exception as e:
            print(f"Admin dashboard error: {e}")
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            flash('Error loading admin dashboard.', 'error')
            return render_template('admin_dashboard.html', 
                                ccas=[], students=[], memberships=[],
                                students_needing_password_setup=[],
                                user_name=session.get('name'))

    @admin_bp.route('/create-student', methods=['GET', 'POST'])
    @admin_required
    def create_student():
        if request.method == 'POST':
            student_id = request.form.get('student_id', '').strip()
            
            if not student_id:
                flash('Student ID is required.', 'error')
                log_admin_action(f"[ERROR] Student ID is required.")
                return render_template('create_student.html')
            
            if not validate_student_id(student_id):
                flash('Student ID must be 7 digits.', 'error')
                log_admin_action(f"[ERROR] Student ID must be 7 digits")
                return render_template('create_student.html')
            
            try:
                # Check admin access
                is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
                if not is_admin:
                    flash('Access denied.', 'error')
                    log_admin_action(f"[ERROR] Access denied.")
                    print(f'DEBUG: Not admin, unauthorised to view.')
                    return redirect(url_for('student_routes.dashboard'))
            
                # Check if student exists
                #SQL refactoring
                # cursor.execute("SELECT StudentId, Name, Email FROM Student WHERE StudentId = ?", (int(student_id),))
                # student_record = cursor.fetchone()
                student_record = Student.query.filter_by(StudentId=int(student_id)).first()
                # Finds a student by their student ID.
                
                if not student_record:
                    flash(f'Student ID {student_id} not found in student records. Please contact administration to add student to system first.', 'error')
                    log_admin_action(f'Student ID  not found in student records. Please contact administration to add student to system first.')
                    return render_template('create_student.html')
                
                # Check if student already has a registered account
                #SQL refactoring
                # cursor.execute("SELECT UserId FROM UserDetails WHERE StudentId = ?", (int(student_id),))
                # existing_account = cursor.fetchone()
                existing_account = User.query.filter_by(StudentId=int(student_id)).first()
                # Checks if a user account already exists for the given student ID.
                
                if existing_account:
                    flash(f'Student {student_record.Name} (ID: {student_id}) already has a login account.', 'error')
                    log_admin_action(f'Student already has a login account.')
                    return render_template('create_student.html')
                
                # Create account with NULL password, student will set via email link
                #SQL refactoring
                # cursor.execute("""
                #     INSERT INTO UserDetails (Username, StudentId, Password, SystemRole)
                #     VALUES (?, ?, NULL, 'student')
                # """, (int(student_id), int(student_id)))
                new_user = User(Username=student_id, StudentId=int(student_id), Password=None, SystemRole='student')
                db.session.add(new_user)
                db.session.commit()
                # \*\ Added for logging
                log_admin_action(session["user_id"], f"Created login for student ID {student_id}")
                # \*\ Ended for logging
                # Creates a new user with a NULL password.
                
                # Send password setup email immediately after successful account creation
                student_name = student_record.Name
                student_email = student_record.Email
                
                base_message = f'Login account created successfully for {student_name} (ID: {student_id})!'
                
                if student_email:
                    try:
                        # Generate password reset token and send setup email
                        token = email_service.generate_password_reset_token(student_id)
                        email_sent = email_service.send_student_credentials(
                            student_name=student_name,
                            student_email=student_email,
                            student_id=student_id,
                            temp_password=None  # No temp password needed
                        )
                        
                        if email_sent:
                            flash(f'{base_message} Password setup email sent to {student_email}. Student must set their password before they can login.', 'success')
                            log_admin_action(f'Password setup email sent to student. Student must set their password before they can login.')
                        else:
                            flash(f'{base_message} However, email notification failed. Please provide password setup link manually.', 'warning')
                            log_admin_action(f'However, email notification failed. Please provide password setup link manually.')
                    except Exception as e:
                        log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
                        print(f"Email sending error: {e}")
                        flash(f'{base_message} However, email notification failed. Please provide password setup link manually.', 'warning')
                else:
                    flash(f'{base_message} No email on file. Please provide password setup link manually.', 'warning')
                    log_admin_action(f'However, email notification failed. Please provide password setup link manually.')
                return redirect(url_for('admin_routes.admin_dashboard'))
                
            except Exception as e:
                db.session.rollback()
                print(f"Create student account error: {e}")
                log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
                flash('Error creating student account. Please try again.', 'error')
                return render_template('create_student.html')
        
        return render_template('create_student.html')

    @admin_bp.route('/create-cca', methods=['GET', 'POST'])
    @admin_required
    def create_cca():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('CCA name is required.', 'error')
                log_admin_action('CCA name is required.')
                return render_template('create_cca.html')
            
            try:
                # Check admin access
                is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
                if not is_admin:
                    flash('Access denied.', 'error')
                    print(f'DEBUG: Not admin, unauthorised to view.')
                    log_admin_action('Access denied.')
                    return redirect(url_for('student_routes.dashboard'))
            
                # Check if CCA name already exists
                #SQL refactoring
                # cursor.execute("SELECT CCAId FROM CCA WHERE Name = ?", (name,))
                # if cursor.fetchone():
                #     flash('CCA name already exists.', 'error')
                #     return render_template('create_cca.html')
                if CCA.query.filter_by(Name=name).first():
                    flash('CCA name already exists.', 'error')
                    log_admin_action('CCA name already exists.')
                    return render_template('create_cca.html')
                # Checks if a CCA with the given name already exists.
                
                # Insert new CCA
                #SQL refactoring
                # cursor.execute("""
                #     INSERT INTO CCA (Name, Description)
                #     VALUES (?, ?)
                # """, (name, description or ''))
                new_cca = CCA(Name=name, Description=description or '')
                db.session.add(new_cca)
                db.session.commit()
                # \*\ Added for logging
                log_admin_action(session["user_id"], f"Created CCA: {name}")
                # \*\ Ended for logging
                # Creates a new CCA.
                
                flash(f'CCA "{name}" created successfully!', 'success')
                log_admin_action(f'CCA created successfully!')
                return redirect(url_for('admin_routes.admin_dashboard'))
                
            except Exception as e:
                db.session.rollback()
                log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
                print(f"Create CCA error: {e}")
                flash('Error creating CCA. Please try again.', 'error')
                return render_template('create_cca.html')
        
        return render_template('create_cca.html')

    @admin_bp.route('/cca/<int:cca_id>')
    @admin_required
    def view_cca(cca_id):
        try:
            # Check admin access
            is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
            if not is_admin:
                flash('Access denied.', 'error')
                print(f'DEBUG: Not admin, unauthorised to view.')
                log_admin_action('Access denied.')
                return redirect(url_for('student_routes.dashboard'))
            
            # Get CCA details
            #SQL refactoring
            # cursor.execute("SELECT CCAId, Name, Description FROM CCA WHERE CCAId = ?", (cca_id,))
            # cca = cursor.fetchone()
            cca = CCA.query.get(cca_id)
            # Retrieves a CCA by its primary key.
            
            if not cca:
                flash('CCA not found.', 'error')
                log_admin_action('CCA not found.')
                return redirect(url_for('admin_routes.admin_dashboard'))
            
            # Get CCA members
            #SQL refactoring
            # members_query = """
            # SELECT s.StudentId, s.Name, s.Email, cm.CCARole, cm.MemberId, ud.UserId
            # FROM CCAMembers cm
            # INNER JOIN v_ActiveUserDetails ud ON cm.UserId = ud.UserId
            # INNER JOIN v_ActiveStudents s ON ud.StudentId = s.StudentId
            # WHERE cm.CCAId = ?
            # ORDER BY s.Name
            # """
            # cursor.execute(members_query, (cca_id,))
            # members = cursor.fetchall()
            members = db.session.query(
                Student.StudentId, Student.Name, Student.Email, CCAMembers.CCARole, CCAMembers.MemberId, User.UserId
            ).join(User, CCAMembers.UserId == User.UserId).join(Student).filter(CCAMembers.CCAId == cca_id).order_by(Student.Name).all()
            # Retrieves all members of a specific CCA.
            
            # Get all students not in this CCA (for assignment)
            #SQL refactoring
            # not_in_cca_query = """
            # SELECT s.StudentId, s.Name
            # FROM v_ActiveStudents s
            # INNER JOIN v_ActiveUserDetails ud ON s.StudentId = ud.StudentId
            # WHERE ud.UserId NOT IN (
            #     SELECT UserId FROM CCAMembers WHERE CCAId = ?
            # )
            # ORDER BY s.Name
            # """
            # cursor.execute(not_in_cca_query, (cca_id,))
            # available_students = cursor.fetchall()
            subquery = db.session.query(CCAMembers.UserId).filter(CCAMembers.CCAId == cca_id)
            available_students = db.session.query(Student.StudentId, Student.Name).join(User).filter(User.UserId.notin_(subquery)).order_by(Student.Name).all()
            # Finds students who are not members of the current CCA.
            
            return render_template('view_cca.html', 
                                 cca=cca, 
                                 members=members, 
                                 available_students=available_students)
            
        except Exception as e:
            print(f"View CCA error: {e}")
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            flash('Error loading CCA details.', 'error')
            return redirect(url_for('admin_routes.admin_dashboard'))

    @admin_bp.route('/cca/<int:cca_id>/edit', methods=['POST'])
    @admin_required
    def edit_cca(cca_id):
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash('CCA name is required.', 'error')
            log_admin_action('CCA name is required.')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        
        try:
            # Check admin access
            is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
            if not is_admin:
                flash('Access denied.', 'error')
                print(f'DEBUG: Not admin, unauthorised to view.')
                log_admin_action(f'DEBUG: Not admin, unauthorised to view.')
                return redirect(url_for('student_routes.dashboard'))
            
            # Check if new name conflicts with existing CCAs (excluding current one)
            #SQL refactoring
            # cursor.execute("SELECT CCAId FROM CCA WHERE Name = ? AND CCAId != ?", (name, cca_id))
            # if cursor.fetchone():
            #     flash('CCA name already exists.', 'error')
            #     return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            if CCA.query.filter(CCA.Name == name, CCA.CCAId != cca_id).first():
                flash('CCA name already exists.', 'error')
                log_admin_action('CCA name already exists.')
                return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            # Checks for CCA name conflicts, excluding the current CCA.
            
            # Update CCA
            #SQL refactoring
            # cursor.execute("""
            #     UPDATE CCA 
            #     SET Name = ?, Description = ?
            #     WHERE CCAId = ?
            # """, (name, description, cca_id))
            cca_to_update = CCA.query.get(cca_id)
            cca_to_update.Name = name
            cca_to_update.Description = description
            db.session.commit()
            # Updates the name and description of a CCA.
            # \*\ Added for logging    
            log_admin_action(session["user_id"], f"Edited CCA ID {cca_id}: renamed to '{name}'")
            # \*\ Ended for logging    

            flash('CCA updated successfully!', 'success')
            log_admin_action('CCA updated successfully!')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
        except Exception as e:
            db.session.rollback()
            print(f"Edit CCA error: {e}")
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            flash('Error updating CCA.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))

    @admin_bp.route('/cca/<int:cca_id>/add-student', methods=['POST'])
    @admin_required
    def add_student_to_cca(cca_id):
        student_id = request.form.get('student_id')
        role = request.form.get('role')
        
        if not all([student_id, role]):
            flash('Please select both student and role.', 'error')
            log_admin_action('Please select both student and role.')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        
        try:
            # Check admin access
            is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
            if not is_admin:
                flash('Access denied.', 'error')
                log_admin_action('Access denied.')
                print(f'DEBUG: Not admin, unauthorised to view.')
                return redirect(url_for('student_routes.dashboard'))
            
            #SQL refactoring
            # cursor.execute("SELECT UserId FROM v_ActiveUserDetails WHERE StudentId = ?", (int(student_id),))
            # user_result = cursor.fetchone()
            user_result = User.query.filter_by(StudentId=int(student_id)).first()
            # Finds a user by their student ID.

            if not user_result:
                flash('Student not found.', 'error')
                log_admin_action('Student not found.')
                return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
            user_id = user_result.UserId
            
            #SQL refactoring
            # cursor.execute("""
            #     INSERT INTO CCAMembers (UserId, CCAId, CCARole)
            #     VALUES (?, ?, ?)
            # """, (user_id, cca_id, role))
            new_member = CCAMembers(UserId=user_id, CCAId=cca_id, CCARole=role)
            db.session.add(new_member)
            db.session.commit()
            # Adds a new member to a CCA.
            # \*\ Added for logging
            log_admin_action(session["user_id"], f"Added student {student_id} to CCA {cca_id} as {role}")
            # \*\ Ended for logging
            flash('Student added to CCA successfully!', 'success')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
        except Exception as e:
            db.session.rollback()
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            print(f"Add student to CCA error: {e}")
            flash('Error adding student to CCA.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))

    @admin_bp.route('/cca/<int:cca_id>/remove-student/<int:member_id>', methods=['POST'])
    @admin_required
    def remove_student_from_cca(cca_id, member_id):
        try:
            # Check admin access
            is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
            if not is_admin:
                flash('Access denied.', 'error')
                log_admin_action('Access denied.')
                print(f'DEBUG: Not admin, unauthorised to view.')
                return redirect(url_for('student_routes.dashboard'))
            
            #SQL refactoring
            # cursor.execute("DELETE FROM CCAMembers WHERE MemberId = ? AND CCAId = ?", (member_id, cca_id))
            CCAMembers.query.filter_by(MemberId=member_id, CCAId=cca_id).delete()
            db.session.commit()
            # \*\ Added for logging
            log_admin_action(session["user_id"], f"Removed member {member_id} from CCA {cca_id}")
            # \*\ Ended for logging

            # Deletes a CCA membership entry by member and CCA ID.
            flash('Student removed from CCA successfully!', 'success')
            log_admin_action('Student removed from CCA successfully!.')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
        except Exception as e:
            db.session.rollback()
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            print(f"Remove student from CCA error: {e}")
            flash('Error removing student from CCA.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))

    @admin_bp.route('/cca/<int:cca_id>/delete', methods=['POST'])
    @admin_required
    def delete_cca(cca_id):
        try:
            # Check admin access
            is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
            if not is_admin:
                flash('Access denied.', 'error')
                log_admin_action('Access denied.')
                print(f'DEBUG: Not admin, unauthorised to view.')
                return redirect(url_for('student_routes.dashboard'))
            
            #SQL refactoring
            # cursor.execute("SELECT Name FROM CCA WHERE CCAId = ?", (cca_id,))
            # cca_result = cursor.fetchone()
            cca_result = CCA.query.get(cca_id)
            # Retrieves a CCA by its primary key.

            if not cca_result:
                flash('CCA not found.', 'error')
                log_admin_action('CCA not found.')
                return redirect(url_for('admin_routes.admin_dashboard'))
            
            cca_name = cca_result.Name
            
            #SQL refactoring
            # cursor.execute("DELETE FROM CCAMembers WHERE CCAId = ?", (cca_id,))
            CCAMembers.query.filter_by(CCAId=cca_id).delete()
            # Deletes all memberships for a given CCA.

            #SQL refactoring
            # cursor.execute("DELETE FROM Votes WHERE PollId IN (SELECT PollId FROM Poll WHERE CCAId = ?)", (cca_id,))
            poll_ids = [p.PollId for p in Poll.query.filter_by(CCAId=cca_id).all()]
            PollVote.query.filter(PollVote.PollId.in_(poll_ids)).delete(synchronize_session=False)
            # Deletes all votes for polls associated with the CCA.

            #SQL refactoring
            # cursor.execute("DELETE FROM Options WHERE PollId IN (SELECT PollId FROM Poll WHERE CCAId = ?)", (cca_id,))
            PollOption.query.filter(PollOption.PollId.in_(poll_ids)).delete(synchronize_session=False)
            # Deletes all options for polls associated with the CCA.

            #SQL refactoring
            # cursor.execute("DELETE FROM Poll WHERE CCAId = ?", (cca_id,))
            Poll.query.filter_by(CCAId=cca_id).delete()
            # Deletes all polls for a given CCA.

            #SQL refactoring
            # cursor.execute("DELETE FROM CCA WHERE CCAId = ?", (cca_id,))
            CCA.query.filter_by(CCAId=cca_id).delete()
            # Deletes the CCA itself.
            
            db.session.commit()
            # \*\ Added for logging
            log_admin_action(session["user_id"], f"Deleted CCA '{cca_name}' (ID: {cca_id})")
            # \*\ Ended for logging
            flash(f'CCA "{cca_name}" and all related data deleted successfully!', 'success')
            return redirect(url_for('admin_routes.admin_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Delete CCA error: {e}")
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            flash('Error deleting CCA.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
    
    @admin_bp.route('/api/search-students')
    @admin_required
    def search_students():
        """API endpoint to search for students by name or student ID"""
        search_query = request.args.get('q', '').strip()
        cca_id = request.args.get('cca_id', '')
        
        if not search_query or len(search_query) < 2:
            return {'students': []}
        
        try:
            # Check admin access
            is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
            if not is_admin:
                flash('Access denied.', 'error')
                print(f'DEBUG: Not admin, unauthorised to view.')
                log_admin_action(f'DEBUG: Not admin, unauthorised to view.')
                return redirect(url_for('student_routes.dashboard'))
            
            #SQL refactoring
            # search_sql = """
            # SELECT s.StudentId, s.Name, s.Email
            # FROM v_ActiveStudents s
            # INNER JOIN v_ActiveUserDetails ud ON s.StudentId = ud.StudentId
            # WHERE (s.Name LIKE ? OR CAST(s.StudentId AS VARCHAR) LIKE ?)
            # AND ud.UserId NOT IN (
            #     SELECT UserId FROM CCAMembers WHERE CCAId = ?
            # )
            # ORDER BY s.Name
            # """
            
            # search_pattern = f'%{search_query}%'
            # cursor.execute(search_sql, (search_pattern, search_pattern, cca_id))
            # students = cursor.fetchall()
            search_pattern = f'%{search_query}%'
            subquery = db.session.query(CCAMembers.UserId).filter(CCAMembers.CCAId == cca_id)
            students = db.session.query(Student.StudentId, Student.Name, Student.Email).join(User).filter(
                db.or_(Student.Name.like(search_pattern), db.cast(Student.StudentId, db.String).like(search_pattern)),
                User.UserId.notin_(subquery)
            ).order_by(Student.Name).all()
            # Searches for students not in a CCA by name or ID.
            
            result = []
            for student in students:
                result.append({
                    'student_id': student.StudentId,
                    'name': student.Name,
                    'email': student.Email
                })
            
            return {'students': result}
            
        except Exception as e:
            print(f"Search students error: {e}")
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            return {'error': 'Search failed'}, 500

    @admin_bp.route('/cca/<int:cca_id>/add-multiple-students', methods=['POST'])
    @admin_required
    def add_multiple_students_to_cca(cca_id):
        """Add multiple students to a CCA in a single operation"""
        student_ids = request.form.getlist('student_ids[]')
        role = request.form.get('role', 'member')
        
        if not student_ids:
            flash('Please select at least one student.', 'error')
            log_admin_action('Please select at least one student.')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
        
        try:
            # Check admin access
            is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
            if not is_admin:
                flash('Access denied.', 'error')
                print(f'DEBUG: Not admin, unauthorised to view.')
                log_admin_action('Access denied.')
                return redirect(url_for('student_routes.dashboard'))
            
            #SQL refactoring
            # placeholders = ','.join(['?' for _ in student_ids])
            # cursor.execute(f"""
            #     SELECT ud.UserId, s.StudentId, s.Name 
            #     FROM v_ActiveUserDetails ud
            #     INNER JOIN v_ActiveStudents s ON ud.StudentId = s.StudentId
            #     WHERE s.StudentId IN ({placeholders})
            # """, student_ids)
            
            # user_data = cursor.fetchall()
            user_data = db.session.query(User.UserId, Student.StudentId, Student.Name).join(Student).filter(Student.StudentId.in_(student_ids)).all()
            # Retrieves user and student data for a list of student IDs.
            
            # Check for students already in the CCA
            existing_members = db.session.query(CCAMembers.UserId).filter(
                CCAMembers.CCAId == cca_id,
                CCAMembers.UserId.in_([u.UserId for u in user_data])
            ).all()
            existing_user_ids = {em[0] for em in existing_members}

            new_members = []
            for user in user_data:
                if user.UserId not in existing_user_ids:
                    new_members.append({
                        'UserId': user.UserId,
                        'CCAId': cca_id,
                        'CCARole': role
                    })

            if new_members:
                db.session.bulk_insert_mappings(CCAMembers, new_members)
                db.session.commit()
                # Added for logging                   
                log_admin_action(session["user_id"], f"Bulk added {len(new_members)} students to CCA {cca_id} as {role}")
                # Ended for logging
                flash(f'{len(new_members)} students added successfully!', 'success')
            else:
                flash('All selected students are already in this CCA.', 'info')
                log_admin_action('All selected students are already in this CCA.')

            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
            
        except Exception as e:
            db.session.rollback()
            print(f"Add multiple students error: {e}")
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            flash('An error occurred while adding students.', 'error')
            return redirect(url_for('admin_routes.view_cca', cca_id=cca_id))
    
    @admin_bp.route('/resend-password-setup/<int:student_id>', methods=['POST'])
    @admin_required
    def resend_password_setup_email(student_id):
        """Resend password setup email for a student who hasn't set their password yet"""
        try:
            # Check admin access
            is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None
            
            if not is_admin:
                flash('Access denied.', 'error')
                print(f'DEBUG: Not admin, unauthorised to view.')
                log_admin_action("Access denied.")
                return redirect(url_for('student_routes.dashboard'))
            
            # Check if student exists and get their details
            #SQL refactoring
            # cursor.execute("""
            #     SELECT s.StudentId, s.Name, s.Email, ud.Password 
            #     FROM Student s
            #     INNER JOIN UserDetails ud ON s.StudentId = ud.StudentId
            #     WHERE s.StudentId = ?
            # """, (student_id,))
            # student_record = cursor.fetchone()
            student_record = db.session.query(
                Student.StudentId, Student.Name, Student.Email, User.Password
            ).join(User).filter(Student.StudentId == student_id).first()
            # Retrieves student and user details for a specific student ID.
            
            if not student_record:
                flash('Student not found.', 'error')
                log_admin_action("Student not found.")
                return redirect(url_for('admin_routes.admin_dashboard'))
            
            # Check if password is not already set
            if student_record.Password is not None:
                flash('Student has already set up their password.', 'info')
                log_admin_action("Student has already set up their password.")
                return redirect(url_for('admin_routes.admin_dashboard'))

            student_name = student_record.Name
            student_email = student_record.Email

            if student_email:
                try:
                    # Generate password reset token and send setup email
                    token = email_service.generate_password_reset_token(student_id)
                    email_sent = email_service.send_student_credentials(
                        student_name=student_name,
                        student_email=student_email,
                        student_id=student_id,
                        temp_password=None  # No temp password needed
                    )
                    
                    if email_sent:
                        flash(f'Password setup email resent to {student_email}.', 'success')
                        log_admin_action(f'Password setup email resent to {student_email}.')
                    else:
                        flash('Email notification failed. Please try again.', 'error')
                        log_admin_action("Email notification failed. Please try again.")
                except Exception as e:
                    print(f"Email sending error: {e}")
                    log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
                    flash('Email notification failed. Please try again.', 'error')
            else:
                flash('No email on file for this student. Cannot send email.', 'warning')
                log_admin_action("No email on file for this student. Cannot send email")
            
            return redirect(url_for('admin_routes.admin_dashboard'))
            
        except Exception as e:
            print(f"Resend password setup error: {e}")
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('admin_routes.admin_dashboard'))
    
    @admin_bp.route('/view-all-ccas')
    @admin_required
    def view_all_ccas():
        """Admin view to see all CCAs with member counts"""
        try:
            # Check admin access
            is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
            if not is_admin:
                flash('Access denied.', 'error')
                print(f'DEBUG: Not admin, unauthorised to view.')
                log_admin_action(f'DEBUG: Not admin, unauthorised to view.')
                return redirect(url_for('student_routes.dashboard'))
            
            # Get all CCAs with member counts
            #SQL refactoring
            # cursor.execute("""
            #     SELECT c.CCAId, c.Name, c.Description,
            #         COUNT(cm.MemberId) as MemberCount,
            #         COUNT(CASE WHEN cm.CCARole = 'moderator' THEN 1 END) as ModeratorCount
            #     FROM CCA c
            #     LEFT JOIN CCAMembers cm ON c.CCAId = cm.CCAId
            #     GROUP BY c.CCAId, c.Name, c.Description
            #     ORDER BY c.Name
            # """)
            # ccas = cursor.fetchall()
            ccas = db.session.query(
                CCA.CCAId, CCA.Name, CCA.Description,
                db.func.count(CCAMembers.MemberId).label('MemberCount'),
                db.func.count(db.case((CCAMembers.CCARole == 'moderator', 1))).label('ModeratorCount')
            ).outerjoin(CCAMembers).group_by(CCA.CCAId, CCA.Name, CCA.Description).order_by(CCA.Name).all()
            # Retrieves all CCAs with their member and moderator counts.
            
            return render_template('admin_view_all_ccas.html', 
                                ccas=ccas,
                                user_name=session.get('name'))
            
        except Exception as e:
            print(f"View all CCAs error: {e}")
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            flash('Error loading CCA list.', 'error')
            return redirect(url_for('admin_routes.admin_dashboard'))

    @admin_bp.route('/view-all-polls')
    @admin_required
    def view_all_polls():
        """Admin view to see all polls in the system"""
        try:
            # Check admin access
            is_admin = db.session.query(User).filter_by(UserId=session["user_id"],SystemRole="admin").first() is not None 
                
            if not is_admin:
                flash('Access denied.', 'error')
                print(f'DEBUG: Not admin, unauthorised to view.')
                log_admin_action('Access denied.')
                return redirect(url_for('student_routes.dashboard'))
            
            #SQL refactoring
            # cursor = conn.cursor()
            
            # # Get all polls with CCA info and vote counts
            # cursor.execute("""
            #     SELECT p.PollId, p.Question, p.QuestionType, p.StartDate, p.EndDate, 
            #         p.IsAnonymous, p.LiveIsActive, c.Name as CCAName,
            #         COUNT(v.VoteId) as VoteCount
            #     FROM v_Poll_With_LiveStatus p
            #     INNER JOIN CCA c ON p.CCAId = c.CCAId
            #     LEFT JOIN Votes v ON p.PollId = v.PollId
            #     GROUP BY p.PollId, p.Question, p.QuestionType, p.StartDate, p.EndDate, 
            #             p.IsAnonymous, p.LiveIsActive, c.Name
            #     ORDER BY p.EndDate DESC, p.StartDate DESC
            # """)
            # polls_data = cursor.fetchall()
            
            # processed_polls = []
            # for row in polls_data:
            #     processed_polls.append({
            #         'PollId': row[0],
            #         'Question': row[1],
            #         'QuestionType': row[2],
            #         'StartDate': row[3].strftime('%Y-%m-%d %H:%M') if row[3] else 'N/A',
            #         'EndDate': row[4].strftime('%Y-%m-%d %H:%M') if row[4] else 'N/A',
            #         'IsAnonymous': row[5],
            #         'LiveIsActive': row[6],
            #         'CCAName': row[7],
            #         'VoteCount': row[8]
            #     })
            
            polls_data = db.session.query(
                Poll.PollId,
                Poll.Question,
                Poll.QuestionType,
                Poll.StartDate,
                Poll.EndDate,
                Poll.IsAnonymous,
                Poll.IsActive.label('LiveIsActive'),
                CCA.Name.label('CCAName'),
                db.func.count(PollVote.VoteId).label('VoteCount')
            ).join(CCA).outerjoin(PollVote).group_by(
                Poll.PollId, Poll.Question, Poll.QuestionType, Poll.StartDate, Poll.EndDate,
                Poll.IsAnonymous, Poll.IsActive, CCA.Name
            ).order_by(Poll.EndDate.desc(), Poll.StartDate.desc()).all()
            # Retrieves all polls with CCA info and vote counts.

            processed_polls = []
            for poll in polls_data:
                processed_polls.append({
                    'PollId': poll.PollId,
                    'Question': poll.Question,
                    'QuestionType': poll.QuestionType,
                    'StartDate': poll.StartDate.strftime('%Y-%m-%d %H:%M') if poll.StartDate else 'N/A',
                    'EndDate': poll.EndDate.strftime('%Y-%m-%d %H:%M') if poll.EndDate else 'N/A',
                    'IsAnonymous': poll.IsAnonymous,
                    'LiveIsActive': poll.LiveIsActive,
                    'CCAName': poll.CCAName,
                    'VoteCount': poll.VoteCount                })
            
            return render_template('admin_view_all_polls.html', 
                                polls=processed_polls,
                                user_name=session['name'])
            
        except Exception as e:
            print(f"View all polls error: {e}")
            log_admin_action(f"[ERROR] Failed to render logs page: {str(e)}")
            flash('Error loading polls.', 'error')
            return redirect(url_for('admin_routes.admin_dashboard'))

    @admin_bp.route('/logs')
    @admin_required
        # \*\ Added Logging
    def view_logs():
        login_logs = (
            db.session.query(LoginLog, User)
            .outerjoin(User, LoginLog.UserId == User.UserId)
            .order_by(LoginLog.Timestamp.desc())
            .limit(50)
            .all()
        )

        admin_logs = (
            db.session.query(AdminLog, User)
            .outerjoin(User, AdminLog.AdminUserId == User.UserId)
            .order_by(AdminLog.Timestamp.desc())
            .limit(50)
            .all()
        )

        logs = sorted(
            [('auth', log, user) for log, user in login_logs] +
            [('admin', log, user) for log, user in admin_logs],
            key=lambda x: x[1].Timestamp,
            reverse=True
        )

        return render_template('admin_logs.html', user_name=session['name'],logs=logs)
        # \*\ Ended added Logging

    # Register the blueprint with the app
    app.register_blueprint(admin_bp)
