from flask import render_template, request, redirect, url_for, session, flash, Blueprint
import pyodbc
from datetime import datetime

# Create a Blueprint
student_bp = Blueprint('student_routes', __name__)

# registration function for student routes
def register_student_routes(app, get_db_connection, login_required):
    
    @student_bp.route('/dashboard')
    @login_required
    def dashboard():
        if session.get('role') == 'admin':
            return redirect(url_for('admin_routes.admin_dashboard'))
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error. Please try again.', 'error')
            return redirect(url_for('misc_routes.logout'))
        
        try:
            cursor = conn.cursor()
            
            cca_query = """
            SELECT c.CCAId, c.Name, c.Description, cm.CCARole
            FROM CCA c
            INNER JOIN CCAMembers cm ON c.CCAId = cm.CCAId
            WHERE cm.UserId = ?
            """
            cursor.execute(cca_query, (session['user_id'],))
            user_ccas = cursor.fetchall()
            
            ccas = []
            user_is_moderator = False
            for cca_row in user_ccas:
                ccas.append({
                    'id': cca_row[0],
                    'name': cca_row[1],
                    'description': cca_row[2],
                    'role': cca_row[3]
                })
                if cca_row[3] == 'moderator':
                    user_is_moderator = True
            
            if ccas:
                cca_ids = [str(c['id']) for c in ccas]
                poll_query = """
                SELECT p.PollId, p.Question, p.EndDate, c.Name as CCAName,
                    DATEDIFF(day, GETDATE(), p.EndDate) as DaysRemaining
                FROM v_Poll_With_LiveStatus p
                INNER JOIN CCA c ON p.CCAId = c.CCAId
                WHERE p.CCAId IN ({}) AND p.LiveIsActive = 1
                ORDER BY p.EndDate ASC
                """.format(','.join(['?'] * len(cca_ids)))
                
                cursor.execute(poll_query, cca_ids)
                poll_results = cursor.fetchall()
                
                available_polls = []
                for poll_row in poll_results:
                    available_polls.append({
                        'id': poll_row[0],
                        'title': poll_row[1],
                        'end_date': poll_row[2].strftime('%Y-%m-%d') if poll_row[2] else '',
                        'cca': poll_row[3],
                        'days_remaining': poll_row[4] if poll_row[4] is not None else 0
                    })
            else:
                available_polls = []
            
            return render_template('dashboard.html', 
                                 ccas=ccas, 
                                 available_polls=available_polls,
                                 user_name=session['name'],
                                 user_role=session['role'],
                                 user_is_moderator=user_is_moderator)
            
        except pyodbc.Error as e:
            print(f"Dashboard data error: {e}")
            flash('Error loading dashboard data.', 'error')
            return render_template('dashboard.html', 
                                 ccas=[], 
                                 available_polls=[],
                                 user_name=session['name'],
                                 user_role=session['role'],
                                 user_is_moderator=False)
        finally:
            if conn:
                conn.close()

    @student_bp.route('/my-ccas')
    @login_required
    def my_ccas():
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.dashboard'))
        
        try:
            cursor = conn.cursor()
            
            cca_query = """
            SELECT c.CCAId, c.Name, c.Description, cm.CCARole
            FROM CCA c
            INNER JOIN CCAMembers cm ON c.CCAId = cm.CCAId
            WHERE cm.UserId = ?
            ORDER BY c.Name
            """
            cursor.execute(cca_query, (session['user_id'],))
            user_ccas_rows = cursor.fetchall()
            
            ccas_list = []
            moderator_ccas_list = []
            for cca_row in user_ccas_rows:
                cca_data = {
                    'id': cca_row[0],
                    'name': cca_row[1],
                    'description': cca_row[2],
                    'role': cca_row[3]
                }
                ccas_list.append(cca_data)
                if cca_row[3] == 'moderator':
                    moderator_ccas_list.append(cca_data)
            
            return render_template('my_ccas.html', 
                                 ccas=ccas_list, 
                                 moderator_ccas=moderator_ccas_list,
                                 user_name=session['name'],
                                 user_role=session['role'])
            
        except Exception as e:
            print(f"My CCAs error: {e}")
            flash('Error loading CCAs.', 'error')
            return redirect(url_for('student_routes.dashboard'))
        finally:
            if conn:
                conn.close()

    @student_bp.route('/polls')
    @login_required
    def view_polls():
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.dashboard'))

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT c.CCAId
                FROM CCA c
                INNER JOIN CCAMembers cm ON c.CCAId = cm.CCAId
                WHERE cm.UserId = ?
            """, (session['user_id'],))
            user_cca_ids_tuples = cursor.fetchall()
            user_cca_ids = [cca_row[0] for cca_row in user_cca_ids_tuples]

            polls_data_rows = []
            if user_cca_ids:
                placeholders = ','.join(['?'] * len(user_cca_ids))
                sql_query = f"""
                    SELECT p.PollId, p.CCAId, p.Question, p.QuestionType, p.StartDate, p.EndDate, p.IsAnonymous, p.LiveIsActive, cca.Name AS CCAName
                    FROM v_Poll_With_LiveStatus p 
                    JOIN CCA cca ON p.CCAId = cca.CCAId
                    WHERE p.CCAId IN ({placeholders})
                    ORDER BY p.EndDate DESC, p.StartDate DESC
                """
                cursor.execute(sql_query, user_cca_ids)
                polls_data_rows = cursor.fetchall()

            processed_polls = []
            for row in polls_data_rows:
                processed_polls.append({
                    'PollId': row[0], 
                    'CCAId': row[1], 
                    'Question': row[2], 
                    'QuestionType': row[3],
                    'StartDate': row[4].strftime('%Y-%m-%d %H:%M') if isinstance(row[4], datetime) else str(row[4]) if row[4] else 'N/A',
                    'EndDate': row[5].strftime('%Y-%m-%d %H:%M') if isinstance(row[5], datetime) else str(row[5]) if row[5] else 'N/A',
                    'IsAnonymous': row[6], 
                    'LiveIsActive': row[7],
                    'CCAName': row[8]
                })

            if not user_cca_ids or not polls_data_rows:
                processed_polls = []

            return render_template('view_poll.html', polls=processed_polls, user_name=session.get('name'))

        except Exception as e:
            print(f"Error fetching polls: {e}")
            flash('Error fetching polls.', 'error')
            return redirect(url_for('student_routes.dashboard'))
        finally:
            if conn:
                conn.close()

    @student_bp.route('/poll/<int:poll_id>')
    @login_required
    def view_poll_detail(poll_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.view_polls'))

        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT p.PollId, p.Question, p.QuestionType, p.StartDate, p.EndDate, 
                       p.IsAnonymous, c.Name AS CCAName, p.LiveIsActive
                FROM v_Poll_With_LiveStatus p
                JOIN CCA c ON p.CCAId = c.CCAId
                WHERE p.PollId = ?
            """, (poll_id,))
            poll_data_row = cursor.fetchone()

            if not poll_data_row:
                flash('Poll not found.', 'error')
                return redirect(url_for('student_routes.view_polls'))

            cursor.execute("""
                SELECT COUNT(*)
                FROM CCAMembers cm
                JOIN Poll p ON cm.CCAId = p.CCAId
                WHERE cm.UserId = ? AND p.PollId = ?
            """, (session['user_id'], poll_id))
            is_member_of_cca = cursor.fetchone()[0] > 0

            if not is_member_of_cca and session['role'] != 'admin':
                 flash('You do not have permission to view this poll.', 'error')
                 return redirect(url_for('student_routes.view_polls'))

            start_date_obj = poll_data_row[3]
            end_date_obj = poll_data_row[4]
            start_date_str = start_date_obj.strftime('%Y-%m-%d %H:%M') if isinstance(start_date_obj, datetime) else str(start_date_obj) if start_date_obj else 'N/A'
            end_date_str = end_date_obj.strftime('%Y-%m-%d %H:%M') if isinstance(end_date_obj, datetime) else str(end_date_obj) if end_date_obj else 'N/A'
            is_ended_status = datetime.now() > end_date_obj if isinstance(end_date_obj, datetime) else False
            
            poll = {
                'PollId': poll_data_row[0], 'Question': poll_data_row[1], 'QuestionType': poll_data_row[2],
                'StartDate': start_date_str, 'EndDate': end_date_str, 'IsAnonymous': poll_data_row[5],
                'Description': None, 'CCAName': poll_data_row[6], 'LiveIsActive': poll_data_row[7],
                'is_ended': is_ended_status
            }

            cursor.execute("""
                SELECT o.OptionId, o.OptionText, COUNT(v.VoteId) AS VoteCount
                FROM Options o
                LEFT JOIN Votes v ON o.OptionId = v.OptionId
                WHERE o.PollId = ?
                GROUP BY o.OptionId, o.OptionText
                ORDER BY o.OptionId
            """, (poll_id,))
            options_data = cursor.fetchall()
            options = [{'OptionId': opt[0], 'OptionText': opt[1], 'VoteCount': opt[2]} for opt in options_data]

            cursor.execute("SELECT COUNT(*) FROM Votes WHERE PollId = ? AND UserId = ?", (poll_id, session['user_id']))
            has_voted = cursor.fetchone()[0] > 0
            
            user_votes = []
            if has_voted and poll['QuestionType'] == 'multiple':
                cursor.execute("SELECT OptionId FROM Votes WHERE PollId = ? AND UserId = ?", (poll_id, session['user_id']))
                user_votes_data = cursor.fetchall()
                user_votes = [uv[0] for uv in user_votes_data]

            return render_template('poll_detail.html', poll=poll, options=options, has_voted=has_voted, user_votes=user_votes, user_name=session.get('name'))

        except Exception as e:
            print(f"Error fetching poll details for poll {poll_id}: {e}")
            flash('Error fetching poll details.', 'error')
            return redirect(url_for('student_routes.view_polls'))
        finally:
            if conn:
                conn.close()

    @student_bp.route('/poll/<int:poll_id>/vote', methods=['POST'])
    @login_required
    def submit_vote(poll_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT LiveIsActive, CCAId, QuestionType FROM v_Poll_With_LiveStatus WHERE PollId = ?", (poll_id,))
            poll_info = cursor.fetchone()

            if not poll_info:
                flash('Poll not found.', 'error')
                return redirect(url_for('student_routes.view_polls'))

            live_is_active, cca_id, question_type = poll_info

            if not live_is_active:
                flash('This poll is closed for voting.', 'error')
                return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

            cursor.execute("SELECT COUNT(*) FROM CCAMembers WHERE UserId = ? AND CCAId = ?", (session['user_id'], cca_id))
            is_member_of_cca = cursor.fetchone()[0] > 0

            if not is_member_of_cca and session['role'] != 'admin':
                 flash('You are not a member of the CCA for this poll and cannot vote.', 'error')
                 return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

            cursor.execute("SELECT COUNT(*) FROM Votes WHERE PollId = ? AND UserId = ?", (poll_id, session['user_id']))
            if cursor.fetchone()[0] > 0:
                flash('You have already voted in this poll.', 'info')
                return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

            selected_option_ids = []
            if question_type == 'single':
                option_id = request.form.get('option')
                if not option_id:
                    flash('Please select an option to vote.', 'error')
                    return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))
                selected_option_ids.append(option_id)
            elif question_type == 'multiple':
                selected_option_ids = request.form.getlist('options')
                if not selected_option_ids:
                    flash('Please select at least one option to vote.', 'error')
                    return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))
            else: # Should not happen
                flash('Invalid poll type.', 'error')
                return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))
            
            valid_option_ids_query = "SELECT OptionId FROM Options WHERE PollId = ?"
            cursor.execute(valid_option_ids_query, (poll_id,))
            valid_options_for_poll = [str(row[0]) for row in cursor.fetchall()]

            for opt_id in selected_option_ids:
                if opt_id not in valid_options_for_poll:
                    flash(f'Invalid option selected: {opt_id}. Please try again.', 'error')
                    return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

            for option_id in selected_option_ids:
                cursor.execute("""
                    INSERT INTO Votes (PollId, OptionId, UserId, VoteDate)
                    VALUES (?, ?, ?, GETDATE())
                """, (poll_id, int(option_id), session['user_id']))
            
            conn.commit()
            flash('Your vote has been recorded successfully!', 'success')

        except pyodbc.Error as db_err:
            if conn: conn.rollback()
            print(f"Database error during voting for poll {poll_id}: {db_err}")
            flash('A database error occurred while submitting your vote. Please try again.', 'error')
        except Exception as e:
            if conn: conn.rollback()
            print(f"Error submitting vote for poll {poll_id}: {e}")
            flash('An error occurred while submitting your vote. Please try again.', 'error')
        finally:
            if conn:
                conn.close()
        
        return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

    app.register_blueprint(student_bp) # Add this line to register the blueprint
