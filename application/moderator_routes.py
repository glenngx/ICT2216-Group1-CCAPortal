from flask import render_template, request, redirect, url_for, session, flash, Blueprint
import pyodbc
from datetime import datetime, timezone, timedelta
from application.auth_utils import moderator_required

# Create a Blueprint
moderator_bp = Blueprint('moderator_routes', __name__)

# Import necessary functions and decorators from the main app or a shared utility module

def register_moderator_routes(app, get_db_connection):

    @moderator_bp.route('/create-poll', methods=['GET', 'POST'])
    @moderator_required
    def create_poll():
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.dashboard'))
        
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT c.CCAId, c.Name, c.Description
                FROM CCA c
                INNER JOIN CCAMembers cm ON c.CCAId = cm.CCAId
                WHERE cm.UserId = ? AND cm.CCARole = 'moderator'
                ORDER BY c.Name
            """, (session['user_id'],))
            moderator_ccas = cursor.fetchall()
            
            user_ccas = []
            for cca in moderator_ccas:
                user_ccas.append({
                    'id': cca[0],
                    'name': cca[1],
                    'description': cca[2]
                })
            
            if request.method == 'POST':
                cca_id = request.form.get('cca_id')
                question = request.form.get('question', '').strip()
                question_type = request.form.get('question_type')
                start_date = request.form.get('start_date')  
                end_date = request.form.get('end_date')      
                is_anonymous = request.form.get('is_anonymous') == '1'
                options = request.form.getlist('options[]')
                
                # Debug print to see what's being received
                print(f"Received form data:")
                print(f"cca_id: {cca_id}")
                print(f"question: {question}")
                print(f"question_type: {question_type}")
                print(f"start_date: {start_date}")
                print(f"end_date: {end_date}")
                print(f"is_anonymous: {is_anonymous}")
                print(f"options: {options}")
                
                if not all([cca_id, question, question_type, start_date, end_date]):
                    flash('Please fill in all required fields.', 'error')
                    return render_template('create_poll.html', user_ccas=user_ccas, 
                                        user_name=session['name'], user_role='moderator',
                                        user_is_moderator=True)
                
                if not any(str(cca['id']) == str(cca_id) for cca in user_ccas):
                    flash('You can only create polls for CCAs where you are a moderator.', 'error')
                    return render_template('create_poll.html', user_ccas=user_ccas,
                                        user_name=session['name'], user_role='moderator',
                                        user_is_moderator=True)
                
                valid_options = [opt.strip() for opt in options if opt.strip()]
                if len(valid_options) < 2:
                    flash('Please provide at least 2 options for the poll.', 'error')
                    return render_template('create_poll.html', user_ccas=user_ccas,
                                        user_name=session['name'], user_role='moderator',
                                        user_is_moderator=True)
                
                if len(valid_options) > 10:
                    flash('Maximum 10 options allowed.', 'error')
                    return render_template('create_poll.html', user_ccas=user_ccas,
                                        user_name=session['name'], user_role='moderator',
                                        user_is_moderator=True)
                
                lower_options = [opt.lower() for opt in valid_options]
                if len(lower_options) != len(set(lower_options)):
                    flash('Please ensure all options are unique.', 'error')
                    return render_template('create_poll.html', user_ccas=user_ccas,
                                        user_name=session['name'], user_role='moderator',
                                        user_is_moderator=True)

                try:
                    from datetime import datetime, timezone, timedelta
                    
                    # Parse the datetime values as local time (GMT+8)
                    start_datetime_local = datetime.fromisoformat(start_date)
                    end_datetime_local = datetime.fromisoformat(end_date)
                    
                    # Create GMT+8 timezone object
                    gmt_plus_8 = timezone(timedelta(hours=8))
                    
                    # Make timezone-aware as GMT+8
                    start_datetime_gmt8 = start_datetime_local.replace(tzinfo=gmt_plus_8)
                    end_datetime_gmt8 = end_datetime_local.replace(tzinfo=gmt_plus_8)
                    
                    # Convert to UTC for database storage
                    start_datetime_utc = start_datetime_gmt8.astimezone(timezone.utc)
                    end_datetime_utc = end_datetime_gmt8.astimezone(timezone.utc)
                    
                    # Remove timezone info for SQL Server compatibility
                    start_datetime = start_datetime_utc.replace(tzinfo=None)
                    end_datetime = end_datetime_utc.replace(tzinfo=None)
                    
                    if start_datetime_local >= end_datetime_local:
                        flash('End date must be after start date.', 'error')
                        return render_template('create_poll.html', user_ccas=user_ccas,
                                            user_name=session['name'], user_role='moderator',
                                            user_is_moderator=True)
                    
                    current_time_gmt8 = datetime.now(gmt_plus_8).replace(tzinfo=None)
                    
                    # Add 1 minute tolerance to account for form submission delay
                    tolerance = timedelta(minutes=1)
                    
                    # Debug prints to help troubleshoot
                    print(f"Start datetime (local input): {start_datetime_local}")
                    print(f"Current time GMT+8: {current_time_gmt8}")
                    print(f"Start time is in past: {start_datetime_local < (current_time_gmt8 - tolerance)}")
                    
                    if start_datetime_local < (current_time_gmt8 - tolerance):
                        flash('Start date cannot be in the past.', 'error')
                        return render_template('create_poll.html', user_ccas=user_ccas,
                                            user_name=session['name'], user_role='moderator',
                                            user_is_moderator=True)
                        
                except ValueError as ve:
                    print(f"Date parsing error: {ve}")
                    flash('Invalid date format.', 'error')
                    return render_template('create_poll.html', user_ccas=user_ccas,
                                        user_name=session['name'], user_role='moderator',
                                        user_is_moderator=True)
                
                try:
                    cursor.execute("""
                        INSERT INTO Poll (CCAId, Question, QuestionType, StartDate, EndDate, IsAnonymous, IsActive)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                    """, (cca_id, question, question_type, start_datetime, end_datetime, is_anonymous))
                    
                    cursor.execute("SELECT @@IDENTITY")
                    poll_id = cursor.fetchone()[0]
                    
                    for option_text in valid_options:
                        cursor.execute("""
                            INSERT INTO Options (PollId, OptionText)
                            VALUES (?, ?)
                        """, (poll_id, option_text))
                    
                    conn.commit()
                    
                    cca_name = next(cca['name'] for cca in user_ccas if cca['id'] == int(cca_id))
                    flash(f'Poll "{question}" created successfully for {cca_name}!', 'success')
                    return redirect(url_for('student_routes.dashboard'))
                    
                except Exception as e:
                    if conn:
                        conn.rollback()
                    print(f"Create poll error: {e}")
                    flash('Error creating poll. Please try again.', 'error')
                    return render_template('create_poll.html', user_ccas=user_ccas,
                                        user_name=session['name'], user_role='moderator',
                                        user_is_moderator=True)
            
            return render_template('create_poll.html', user_ccas=user_ccas,
                                user_name=session['name'], user_role='moderator',
                                user_is_moderator=True)
            
        except Exception as e:
            print(f"Create poll page error: {e}")
            flash('Error loading create poll page.', 'error')
            return redirect(url_for('student_routes.dashboard'))
        finally:
            if conn:
                conn.close()

    @moderator_bp.route('/moderator/cca/<int:cca_id>')
    @moderator_required
    def moderator_view_cca(cca_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.my_ccas'))
        
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
            """, (session['user_id'], cca_id))
            is_moderator = cursor.fetchone()[0] > 0
            
            if not is_moderator:
                flash('Access denied. You are unauthorised to view this CCA.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            cursor.execute("SELECT CCAId, Name, Description FROM CCA WHERE CCAId = ?", (cca_id,))
            cca = cursor.fetchone()
            
            if not cca:
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            members_query = """
            SELECT s.StudentId, s.Name, s.Email, cm.CCARole, cm.MemberId, ud.UserId
            FROM CCAMembers cm
            INNER JOIN v_ActiveUserDetails ud ON cm.UserId = ud.UserId
            INNER JOIN v_ActiveStudents s ON ud.StudentId = s.StudentId
            WHERE cm.CCAId = ?
            ORDER BY s.Name
            """
            cursor.execute(members_query, (cca_id,))
            members = cursor.fetchall()
            
            not_in_cca_query = """
            SELECT s.StudentId, s.Name
            FROM v_ActiveStudents s
            INNER JOIN v_ActiveUserDetails ud ON s.StudentId = ud.StudentId
            WHERE ud.UserId NOT IN (
                SELECT UserId FROM CCAMembers WHERE CCAId = ?
            )
            ORDER BY s.Name
            """
            cursor.execute(not_in_cca_query, (cca_id,))
            available_students = cursor.fetchall()
            
            return render_template('moderator_view_cca.html', 
                                 cca=cca, 
                                 members=members, 
                                 available_students=available_students,
                                 user_name=session['name'],
                                 user_is_moderator=True)
            
        except Exception as e:
            print(f"Moderator view CCA error: {e}")
            flash('Error loading CCA details.', 'error')
            return redirect(url_for('student_routes.my_ccas'))
        finally:
            if conn:
                conn.close()

    @moderator_bp.route('/moderator/cca/<int:cca_id>/edit', methods=['POST'])
    @moderator_required
    def moderator_edit_cca(cca_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.my_ccas'))
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
            """, (session['user_id'], cca_id))
            is_moderator = cursor.fetchone()[0] > 0
            
            if not is_moderator:
                flash('Access denied. You are not a moderator of this CCA.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('CCA name is required.', 'error')
                return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
            cursor.execute("SELECT CCAId FROM CCA WHERE Name = ? AND CCAId != ?", (name, cca_id))
            if cursor.fetchone():
                flash('CCA name already exists.', 'error')
                return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
            cursor.execute("""
                UPDATE CCA 
                SET Name = ?, Description = ?
                WHERE CCAId = ?
            """, (name, description, cca_id))
            
            conn.commit()
            flash('CCA updated successfully!', 'success')
            return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Moderator edit CCA error: {e}")
            flash('Error updating CCA.', 'error')
            return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
        finally:
            if conn:
                conn.close()

    @moderator_bp.route('/moderator/cca/<int:cca_id>/add-student', methods=['POST'])
    @moderator_required
    def moderator_add_student_to_cca(cca_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.my_ccas'))
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
            """, (session['user_id'], cca_id))
            is_moderator = cursor.fetchone()[0] > 0
            
            if not is_moderator:
                flash('Access denied. You are unauthorised to access this CCA.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            student_id = request.form.get('student_id')
            role = request.form.get('role')
            
            if not all([student_id, role]):
                flash('Please select both student and role.', 'error')
                return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
            if role != 'member':
                flash('Access denied. Moderators can only assign the "member" role to students. Contact an administrator to assign moderator roles.', 'error')
                return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
            cursor.execute("SELECT UserId FROM v_ActiveUserDetails WHERE StudentId = ?", (int(student_id),))
            user_result = cursor.fetchone()
            if not user_result:
                flash('Student not found.', 'error')
                return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
            user_id = user_result[0]
            
            cursor.execute("SELECT COUNT(*) FROM CCAMembers WHERE UserId = ? AND CCAId = ?", (user_id, cca_id))
            if cursor.fetchone()[0] > 0:
                flash('Student is already a member of this CCA.', 'error')
                return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
            cursor.execute("""
                INSERT INTO CCAMembers (UserId, CCAId, CCARole)
                VALUES (?, ?, ?)
            """, (user_id, cca_id, 'member'))
            
            conn.commit()
            
            cursor.execute("SELECT Name FROM v_ActiveStudents WHERE StudentId = ?", (int(student_id),))
            student_name_result = cursor.fetchone()
            student_name = student_name_result[0] if student_name_result else f"Student {student_id}"
            
            flash(f'{student_name} has been added to the CCA as a member successfully!', 'success')
            return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Moderator add student to CCA error: {e}")
            flash('Error adding student to CCA.', 'error')
            return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
        finally:
            if conn:
                conn.close()

    @moderator_bp.route('/moderator/cca/<int:cca_id>/remove-student/<int:member_id>', methods=['POST'])
    @moderator_required
    def moderator_remove_student_from_cca(cca_id, member_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.my_ccas'))
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
            """, (session['user_id'], cca_id))
            is_moderator = cursor.fetchone()[0] > 0
            
            if not is_moderator:
                flash('Access denied. You are unauthorised to view this CCA.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            cursor.execute("DELETE FROM CCAMembers WHERE MemberId = ? AND CCAId = ?", (member_id, cca_id))
            conn.commit()
            flash('Student removed from CCA successfully!', 'success')
            return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Moderator remove student from CCA error: {e}")
            flash('Error removing student from CCA.', 'error')
            return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
        finally:
            if conn:
                conn.close()

    @moderator_bp.route('/api/moderator/search-students')
    @moderator_required
    def moderator_search_students():
        """API endpoint for moderators to search for students by name or student ID"""
        search_query = request.args.get('q', '').strip()
        cca_id = request.args.get('cca_id', '')
        
        if not search_query or len(search_query) < 2:
            return {'students': []}
        
        conn = get_db_connection()
        if not conn:
            return {'error': 'Database connection error'}, 500
        
        try:
            cursor = conn.cursor()
            
            # Verify moderator access to this CCA
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
            """, (session['user_id'], cca_id))
            
            if cursor.fetchone()[0] == 0:
                return {'error': 'Access denied'}, 403
            
            # Search for students by name or student ID, excluding those already in the CCA
            search_sql = """
            SELECT s.StudentId, s.Name, s.Email
            FROM v_ActiveStudents s
            INNER JOIN v_ActiveUserDetails ud ON s.StudentId = ud.StudentId
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
            print(f"Moderator search students error: {e}")
            return {'error': 'Search failed'}, 500
        finally:
            if conn:
                conn.close()

    @moderator_bp.route('/moderator/cca/<int:cca_id>/add-multiple-students', methods=['POST'])
    @moderator_required
    def moderator_add_multiple_students_to_cca(cca_id):
        """Allow moderators to add multiple students to their CCA"""
        student_ids = request.form.getlist('student_ids[]')
        
        if not student_ids:
            flash('Please select at least one student.', 'error')
            return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.my_ccas'))
        
        try:
            cursor = conn.cursor()
            
            # Verify moderator access to this CCA
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
            """, (session['user_id'], cca_id))
            
            if cursor.fetchone()[0] == 0:
                flash('Access denied. You are unauthorised to view this CCA.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            # Get user IDs for the selected student IDs
            placeholders = ','.join(['?' for _ in student_ids])
            cursor.execute(f"""
                SELECT ud.UserId, s.StudentId, s.Name 
                FROM v_ActiveUserDetails ud
                INNER JOIN v_ActiveStudents s ON ud.StudentId = s.StudentId
                WHERE s.StudentId IN ({placeholders})
            """, student_ids)
            
            user_data = cursor.fetchall()
            
            # Bulk insert new memberships (moderators can only assign 'member' role)
            membership_data = [(user[0], cca_id, 'member') for user in user_data]
            cursor.executemany("""
                INSERT INTO CCAMembers (UserId, CCAId, CCARole)
                VALUES (?, ?, ?)
            """, membership_data)
            
            conn.commit()
            
            added_count = len(user_data)
            flash(f'{added_count} students have been added to the CCA as members!', 'success')
            return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Moderator add multiple students error: {e}")
            flash('Error adding students to CCA. Please try again.', 'error')
            return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
        finally:
            if conn:
                conn.close()

    # Register the blueprint with the app
    app.register_blueprint(moderator_bp)
