from flask import render_template, request, redirect, url_for, session, flash, Blueprint
from sqlalchemy.orm import aliased
from sqlalchemy import text, cast
from application.models import db, CCA, CCAMembers, User, Student, Poll, PollOption
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
            
            moderator_ccas = db.session.query(CCA).join(CCAMembers).filter(CCAMembers.UserId == session['user_id'], CCAMembers.CCARole == 'moderator').order_by(CCA.Name).all()
            #This query joins CCA and CCAMembers, filtering for the moderator's CCAs.

            user_ccas = []
            for cca in moderator_ccas:
                user_ccas.append({
                    'id': cca.CCAId,
                    'name': cca.Name,
                    'description': cca.Description
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
                    new_poll = Poll(
                        CCAId=cca_id,
                        Question=question,
                        QuestionType=question_type,
                        StartDate=start_datetime,
                        EndDate=end_datetime,
                        IsAnonymous=is_anonymous,
                        IsActive=True
                    )
                    db.session.add(new_poll)
                    db.session.flush()
                    #This creates and adds a new Poll object to the session.

                    poll_id = new_poll.PollId
                    #This gets the new PollId from the flushed session object.

                    for option_text in valid_options:
                        new_option = PollOption(PollId=poll_id, OptionText=option_text)
                        db.session.add(new_option)
                        #This creates and adds new PollOption objects for the new poll.
                    
                    # SQL refactoring
                    # conn.commit()
                    db.session.commit()
                    #This commits the transaction to the database.
                    
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
            pass

    @moderator_bp.route('/moderator/cca/<int:cca_id>')
    @moderator_required
    def moderator_view_cca(cca_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.my_ccas'))
        
        try:
            cursor = conn.cursor()
            
            is_moderator = db.session.query(CCAMembers).filter_by(UserId=session['user_id'], CCAId=cca_id, CCARole='moderator').first() is not None
            #This query checks if a CCAMembers record exists for the user and CCA.
            
            if not is_moderator:
                flash('Access denied. You are unauthorised to view this CCA.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            cca = db.session.query(CCA).filter_by(CCAId=cca_id).first()
            #This query fetches the CCA details by its primary key.
            
            if not cca:
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            v_ActiveUserDetails = aliased(User, name='v_ActiveUserDetails')
            v_ActiveStudents = aliased(Student, name='v_ActiveStudents')
            members = db.session.query(
                v_ActiveStudents.StudentId,
                v_ActiveStudents.Name,
                v_ActiveStudents.Email,
                CCAMembers.CCARole,
                CCAMembers.MemberId,
                v_ActiveUserDetails.UserId
            ).join(v_ActiveUserDetails, CCAMembers.UserId == v_ActiveUserDetails.UserId) \
             .join(v_ActiveStudents, v_ActiveUserDetails.StudentId == v_ActiveStudents.StudentId) \
             .filter(CCAMembers.CCAId == cca_id) \
             .order_by(v_ActiveStudents.Name).all()
            #This query joins three tables to get member details for a CCA.

            subquery = db.session.query(CCAMembers.UserId).filter(CCAMembers.CCAId == cca_id)
            v_ActiveUserDetails = aliased(User, name='v_ActiveUserDetails')
            v_ActiveStudents = aliased(Student, name='v_ActiveStudents')
            available_students = db.session.query(v_ActiveStudents.StudentId, v_ActiveStudents.Name) \
                .join(v_ActiveUserDetails, v_ActiveStudents.StudentId == v_ActiveUserDetails.StudentId) \
                .filter(v_ActiveUserDetails.UserId.notin_(subquery)) \
                .order_by(v_ActiveStudents.Name).all()
            #This query finds students not in the CCA using a subquery.
            
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
            is_moderator = db.session.query(CCAMembers).filter_by(UserId=session['user_id'], CCAId=cca_id, CCARole='moderator').first() is not None
            #This query checks if a CCAMembers record exists for the user and CCA.
            
            if not is_moderator:
                flash('Access denied. You are not a moderator of this CCA.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('CCA name is required.', 'error')
                return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
            if db.session.query(CCA).filter(CCA.Name == name, CCA.CCAId != cca_id).first():
                #This query checks if the new CCA name already exists.
                flash('CCA name already exists.', 'error')
                return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
            cca_to_update = db.session.query(CCA).filter_by(CCAId=cca_id).one()
            cca_to_update.Name = name
            cca_to_update.Description = description
            #This code updates the name and description for the specified CCA.
            
            # SQL refactoring
            # conn.commit()
            db.session.commit()
            #This commits the transaction to the database.
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
            is_moderator = db.session.query(CCAMembers).filter_by(UserId=session['user_id'], CCAId=cca_id, CCARole='moderator').first() is not None
            #This query checks if a CCAMembers record exists for the user and CCA.
            
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
            
            # SQL refactoring
            # cursor.execute("SELECT UserId FROM v_ActiveUserDetails WHERE StudentId = ?", (int(student_id),))
            # user_result = cursor.fetchone()
            user_result = db.session.query(User.UserId).filter_by(StudentId=int(student_id)).first()
            #This query fetches the UserId for a given StudentId.
            if not user_result:
                flash('Student not found.', 'error')
                return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
            user_id = user_result[0]
            
            # SQL refactoring
            # cursor.execute("SELECT COUNT(*) FROM CCAMembers WHERE UserId = ? AND CCAId = ?", (user_id, cca_id))
            # if cursor.fetchone()[0] > 0:
            if db.session.query(CCAMembers).filter_by(UserId=user_id, CCAId=cca_id).first():
                #This query checks if the student is already a member of the CCA.
                flash('Student is already a member of this CCA.', 'error')
                return redirect(url_for('moderator_routes.moderator_view_cca', cca_id=cca_id))
            
            # SQL refactoring
            # cursor.execute("""
            #     INSERT INTO CCAMembers (UserId, CCAId, CCARole)
            #     VALUES (?, ?, ?)
            # """, (user_id, cca_id, 'member'))
            new_member = CCAMembers(UserId=user_id, CCAId=cca_id, CCARole='member')
            db.session.add(new_member)
            #This creates and adds a new CCAMembers object to the session.
            
            # SQL refactoring
            # conn.commit()
            db.session.commit()
            #This commits the transaction to the database.
            
            # SQL refactoring
            # cursor.execute("SELECT Name FROM v_ActiveStudents WHERE StudentId = ?", (int(student_id),))
            # student_name_result = cursor.fetchone()
            student_name_result = db.session.query(Student.Name).filter_by(StudentId=int(student_id)).first()
            #This query fetches the student's name using their StudentId.
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
            is_moderator = db.session.query(CCAMembers).filter_by(UserId=session['user_id'], CCAId=cca_id, CCARole='moderator').first() is not None
            #This query checks if a CCAMembers record exists for the user and CCA.
            
            if not is_moderator:
                flash('Access denied. You are unauthorised to view this CCA.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            # SQL refactoring
            # cursor.execute("DELETE FROM CCAMembers WHERE MemberId = ? AND CCAId = ?", (member_id, cca_id))
            # conn.commit()
            member_to_remove = db.session.query(CCAMembers).filter_by(MemberId=member_id, CCAId=cca_id).one()
            db.session.delete(member_to_remove)
            db.session.commit()
            #This code deletes a member from a CCA and commits the change.
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
            
            # SQL refactoring
            # Verify moderator access to this CCA
            # cursor.execute("""
            #     SELECT COUNT(*) FROM CCAMembers 
            #     WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
            # """, (session['user_id'], cca_id))
            
            # if cursor.fetchone()[0] == 0:
            if not db.session.query(CCAMembers).filter_by(UserId=session['user_id'], CCAId=cca_id, CCARole='moderator').first():
                #This query checks if a CCAMembers record exists for the user and CCA.
                return {'error': 'Access denied'}, 403
            
            # SQL refactoring
            # Search for students by name or student ID, excluding those already in the CCA
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
            v_ActiveUserDetails = aliased(User, name='v_ActiveUserDetails')
            v_ActiveStudents = aliased(Student, name='v_ActiveStudents')

            students = db.session.query(v_ActiveStudents.StudentId, v_ActiveStudents.Name, v_ActiveStudents.Email) \
                .join(v_ActiveUserDetails, v_ActiveStudents.StudentId == v_ActiveUserDetails.StudentId) \
                .filter(
                    (v_ActiveStudents.Name.like(search_pattern) | cast(v_ActiveStudents.StudentId, db.String).like(search_pattern)),
                    v_ActiveUserDetails.UserId.notin_(subquery)
                ).order_by(v_ActiveStudents.Name).all()
            #This query searches for students not in a CCA by name or ID.
            
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
            
            # SQL refactoring
            # Verify moderator access to this CCA
            # cursor.execute("""
            #     SELECT COUNT(*) FROM CCAMembers 
            #     WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
            # """, (session['user_id'], cca_id))
            
            # if cursor.fetchone()[0] == 0:
            if not db.session.query(CCAMembers).filter_by(UserId=session['user_id'], CCAId=cca_id, CCARole='moderator').first():
                #This query checks if a CCAMembers record exists for the user and CCA.
                flash('Access denied. You are unauthorised to view this CCA.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            # SQL refactoring
            # Get user IDs for the selected student IDs
            # placeholders = ','.join(['?' for _ in student_ids])
            # cursor.execute(f"""
            #     SELECT ud.UserId, s.StudentId, s.Name 
            #     FROM v_ActiveUserDetails ud
            #     INNER JOIN v_ActiveStudents s ON ud.StudentId = s.StudentId
            #     WHERE s.StudentId IN ({placeholders})
            # """, student_ids)
            
            # user_data = cursor.fetchall()
            v_ActiveUserDetails = aliased(User, name='v_ActiveUserDetails')
            v_ActiveStudents = aliased(Student, name='v_ActiveStudents')
            user_data = db.session.query(v_ActiveUserDetails.UserId, v_ActiveStudents.StudentId, v_ActiveStudents.Name) \
                .join(v_ActiveStudents, v_ActiveUserDetails.StudentId == v_ActiveStudents.StudentId) \
                .filter(v_ActiveStudents.StudentId.in_(student_ids)).all()
            #This query retrieves user and student data for a list of student IDs.
            
            # SQL refactoring
            # Bulk insert new memberships (moderators can only assign 'member' role)
            # membership_data = [(user[0], cca_id, 'member') for user in user_data]
            # cursor.executemany("""
            #     INSERT INTO CCAMembers (UserId, CCAId, CCARole)
            #     VALUES (?, ?, ?)
            # """, membership_data)
            for user in user_data:
                new_member = CCAMembers(UserId=user[0], CCAId=cca_id, CCARole='member')
                db.session.add(new_member)
            #This code adds multiple new members to the CCA.
            
            # SQL refactoring
            # conn.commit()
            db.session.commit()
            #This commits the transaction to the database.
            
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
