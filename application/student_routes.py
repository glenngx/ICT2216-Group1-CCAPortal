from flask import render_template, request, redirect, url_for, session, flash, Blueprint
import pyotp, qrcode
from io import BytesIO
from base64 import b64encode
import pyodbc
from datetime import datetime, timedelta 
import secrets
import hashlib
import bcrypt
from application.misc_routes import validate_password_nist
from application.misc_routes import login_required_with_mfa

def convert_utc_to_gmt8_display(utc_datetime):
    """Convert UTC datetime to GMT+8 for display purposes"""
    if utc_datetime and isinstance(utc_datetime, datetime):
        # Add 8 hours to convert UTC to GMT+8
        gmt8_datetime = utc_datetime + timedelta(hours=8)
        return gmt8_datetime.strftime('%Y-%m-%d %H:%M')
    return str(utc_datetime) if utc_datetime else 'N/A'

# Create a Blueprint
student_bp = Blueprint('student_routes', __name__)

# registration function for student routes
def register_student_routes(app, get_db_connection, login_required):
    
    # \*/ Added for MFA
    @student_bp.route('/mfa-setup', methods=['GET', 'POST'])
    @login_required
    def mfa_setup():
        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "error")
            return redirect(url_for('student_routes.dashboard'))

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT MFATOTPSecret FROM UserDetails WHERE UserId = ?", (session['user_id'],))
            row = cursor.fetchone()

            if row and row[0]:
                # Someone came here even though MFA already enabled
                return redirect(url_for('misc_routes.mfa_verify'))

                # keep a temp secret in the session
            if 'mfa_temp_secret' not in session:
                session['mfa_temp_secret'] = pyotp.random_base32()

                secret = session['mfa_temp_secret']
                totp   = pyotp.TOTP(secret)
                uri    = totp.provisioning_uri(
                            name=session['email'],
                            issuer_name="CCAP Web Portal"
                        )

                # create QR → base64
                qr_buf = BytesIO()
                qrcode.make(uri).save(qr_buf, format='PNG')
                qr_b64 = b64encode(qr_buf.getvalue()).decode()

                # POST: user submits first 6-digit code
                if request.method == 'POST':
                    code = request.form.get('mfa_code', '').strip()
                    if totp.verify(code):
                        cursor.execute(
                            "UPDATE UserDetails SET MFATOTPSecret = ? WHERE UserId = ?",
                            (secret, session['user_id'])
                        )
                        conn.commit()
                        session.pop('mfa_temp_secret', None)
                        session['mfa_authenticated'] = True
                        flash("MFA setup complete.", "success")
                        return redirect(url_for('student_routes.dashboard'))
                    else:
                        flash("Invalid code, please try again.", "error")

                return render_template('mfa_setup.html', qr_b64=qr_b64, secret=secret)

        finally:
            conn.close()
    # \*/ ENDED for MFA 

    @student_bp.route('/dashboard')
    @login_required_with_mfa
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
                        'end_date': convert_utc_to_gmt8_display(poll_row[2]).split(' ')[0] if poll_row[2] else '',  # Just date part
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
        if session.get('role') == 'admin':
            return redirect(url_for('admin_routes.admin_dashboard'))
        
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
            user_is_moderator = False  # ADD THIS LINE
            
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
                    user_is_moderator = True  # ADD THIS LINE
            
            return render_template('my_ccas.html', 
                                ccas=ccas_list, 
                                moderator_ccas=moderator_ccas_list,
                                user_is_moderator=user_is_moderator,  # ADD THIS LINE
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
        if session.get('role') == 'admin':
            return redirect(url_for('admin_routes.admin_dashboard'))
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.dashboard'))

        try:
            cursor = conn.cursor()
            
            # Check if user is moderator
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCARole = 'moderator'
            """, (session['user_id'],))
            user_is_moderator = cursor.fetchone()[0] > 0
            
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
                    'StartDate': convert_utc_to_gmt8_display(row[4]),
                    'EndDate': convert_utc_to_gmt8_display(row[5]),
                    'IsAnonymous': row[6], 
                    'LiveIsActive': row[7],
                    'CCAName': row[8]
                })

            if not user_cca_ids or not polls_data_rows:
                processed_polls = []

            return render_template('view_poll.html', 
                                polls=processed_polls, 
                                user_is_moderator=user_is_moderator,
                                user_name=session.get('name'))

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

            # Check if user is moderator - ADD THIS BLOCK
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCARole = 'moderator'
            """, (session['user_id'],))
            user_is_moderator = cursor.fetchone()[0] > 0

            cursor.execute("""
                SELECT p.PollId, p.Question, p.QuestionType, p.StartDate, p.EndDate, 
                    p.IsAnonymous, c.Name AS CCAName, p.LiveIsActive
                FROM v_Poll_With_LiveStatus p
                JOIN CCA c ON p.CCAId = c.CCAId
                WHERE p.PollId = ?
            """, (poll_id,))
            poll_data_row = cursor.fetchone()

            if not poll_data_row:
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.view_polls'))

            cursor.execute("""
                SELECT COUNT(*)
                FROM CCAMembers cm
                JOIN Poll p ON cm.CCAId = p.CCAId
                WHERE cm.UserId = ? AND p.PollId = ?
            """, (session['user_id'], poll_id))
            is_member_of_cca = cursor.fetchone()[0] > 0

            if not is_member_of_cca and session['role'] != 'admin':
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.view_polls'))

            start_date_obj = poll_data_row[3]
            end_date_obj = poll_data_row[4]
            start_date_str = start_date_obj.strftime('%Y-%m-%d %H:%M') if isinstance(start_date_obj, datetime) else str(start_date_obj) if start_date_obj else 'N/A'
            end_date_str = end_date_obj.strftime('%Y-%m-%d %H:%M') if isinstance(end_date_obj, datetime) else str(end_date_obj) if end_date_obj else 'N/A'
            is_ended_status = datetime.now() > end_date_obj if isinstance(end_date_obj, datetime) else False
            
            poll = {
                'PollId': poll_data_row[0], 
                'Question': poll_data_row[1], 
                'QuestionType': poll_data_row[2],
                'StartDate': convert_utc_to_gmt8_display(poll_data_row[3]),
                'EndDate': convert_utc_to_gmt8_display(poll_data_row[4]),
                'IsAnonymous': poll_data_row[5],
                'Description': None, 
                'CCAName': poll_data_row[6], 
                'LiveIsActive': poll_data_row[7],
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

            # Check if user has voted
            has_voted = False
            if poll['IsAnonymous']:
                # For anonymous polls, check if the user's token has been used
                cursor.execute("SELECT IsUsed FROM VoteTokens WHERE PollId = ? AND UserId = ?", (poll_id, session['user_id']))
                token_status = cursor.fetchone()
                if token_status and token_status[0]: # IsUsed is True
                    has_voted = True
            else:
                # For non-anonymous polls, check the Votes table directly
                cursor.execute("SELECT COUNT(*) FROM Votes WHERE PollId = ? AND UserId = ?", (poll_id, session['user_id']))
                if cursor.fetchone()[0] > 0:
                    has_voted = True
                
            
            user_votes = []
            if has_voted and poll['QuestionType'] == 'multiple':
                cursor.execute("SELECT OptionId FROM Votes WHERE PollId = ? AND UserId = ?", (poll_id, session['user_id']))
                user_votes_data = cursor.fetchall()
                user_votes = [uv[0] for uv in user_votes_data]

            vote_token = None
            if poll['IsAnonymous'] and poll['LiveIsActive']:
                # Check if token already exists and if it is unused
                cursor.execute("""
                    SELECT IsUsed FROM VoteTokens 
                    WHERE PollId = ? AND UserId = ?
                """, (poll_id, session['user_id']))
                token_status_row = cursor.fetchone()

                if token_status_row:
                    is_used = token_status_row[0]
                    if not is_used:
                        # Token exists but unused → safely delete and reissue
                        cursor.execute("""
                            DELETE FROM VoteTokens 
                            WHERE PollId = ? AND UserId = ?
                        """, (poll_id, session['user_id']))
                        conn.commit()

                        # Reissue a new token
                        raw_token = secrets.token_hex(32)
                        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

                        cursor.execute("""
                            INSERT INTO VoteTokens (Token, PollId, UserId, IssuedTime, ExpiryTime)
                            VALUES (?, ?, ?, GETUTCDATE(), DATEADD(MINUTE, 10, GETUTCDATE()))
                        """, (hashed_token, poll_id, session['user_id']))
                        conn.commit()

                        vote_token = raw_token
                    else:
                        vote_token = None  # Already used, no reissue
                else:
                    # No token exists yet → issue first time
                    raw_token = secrets.token_hex(32)
                    hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

                    cursor.execute("""
                        INSERT INTO VoteTokens (Token, PollId, UserId, IssuedTime, ExpiryTime)
                        VALUES (?, ?, ?, GETUTCDATE(), DATEADD(MINUTE, 10, GETUTCDATE()))
                    """, (hashed_token, poll_id, session['user_id']))

                    vote_token = raw_token

            return render_template('poll_detail.html', 
                                poll=poll, 
                                options=options, 
                                has_voted=has_voted, 
                                user_votes=user_votes, 
                                user_name=session.get('name'),
                                user_is_moderator=user_is_moderator, vote_token=vote_token)
        
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

        if session.get('role') == 'admin':
            flash('Admins are not allowed to vote.', 'error')
            return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

        try:
            cursor = conn.cursor()

            # Get poll info
            cursor.execute("SELECT LiveIsActive, CCAId, QuestionType FROM v_Poll_With_LiveStatus WHERE PollId = ?", (poll_id,))
            poll_info = cursor.fetchone()

            if not poll_info:
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.view_polls'))

            live_is_active, cca_id, question_type = poll_info

            if not live_is_active:
                flash('This poll is closed for voting.', 'error')
                return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

            # Check if user is a member of the CCA
            cursor.execute("SELECT COUNT(*) FROM CCAMembers WHERE UserId = ? AND CCAId = ?", (session['user_id'], cca_id))
            is_member_of_cca = cursor.fetchone()[0] > 0

            if not is_member_of_cca:
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

            # Check if user already voted
            cursor.execute("SELECT COUNT(*) FROM Votes WHERE PollId = ? AND UserId = ?", (poll_id, session['user_id']))
            has_voted = cursor.fetchone()[0] > 0


            # Check if poll is anonymous
            cursor.execute("SELECT IsAnonymous FROM Poll WHERE PollId = ?", (poll_id,))
            is_anonymous = cursor.fetchone()[0]

            selected_option_ids = []
            if question_type == 'single_choice':
                option_id = request.form.get('option_id')
                if option_id:
                    selected_option_ids.append(option_id)
            elif question_type == 'multiple_choice':
                selected_option_ids = request.form.getlist('option_ids[]')
            else:
                flash('Invalid poll type.', 'error')
                return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

            # Validate selected options
            cursor.execute("SELECT OptionId FROM Options WHERE PollId = ?", (poll_id,))
            valid_option_ids = [str(row[0]) for row in cursor.fetchall()]

            for opt_id in selected_option_ids:
                if opt_id not in valid_option_ids:
                    flash(f'Invalid option selected: {opt_id}', 'error')
                    return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

            # ✅ Token validation only if not already voted
            if is_anonymous and not has_voted:
                raw_token = request.form.get('vote_token')
                if not raw_token:
                    flash('Missing vote token for anonymous poll.', 'error')
                    return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

                hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()
                cursor.execute("""
                    SELECT IsUsed, ExpiryTime FROM VoteTokens 
                    WHERE Token = ? AND PollId = ? AND UserId = ?
                """, (hashed_token, poll_id, session['user_id']))
                token_row = cursor.fetchone()

                is_used, expiry_time = token_row
                if is_used:
                    flash('This token has already been used.', 'error')
                    return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))
                if expiry_time and datetime.utcnow() > expiry_time:
                    flash('This vote token has expired. Please refresh the page to get a new one.', 'error')
                    return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

                if not token_row:
                    flash('Invalid or expired vote token.', 'error')
                    return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

                if token_row[0]:  # IsUsed == True
                    flash('This token has already been used.', 'error')
                    return redirect(url_for('student_routes.view_poll_detail', poll_id=poll_id))

            # ✅ Insert vote only if not already voted
            if not has_voted:
                for option_id in selected_option_ids:
                    cursor.execute("""
                        INSERT INTO Votes (PollId, OptionId, UserId, VotedTime)
                        VALUES (?, ?, ?, GETDATE())
                    """, (poll_id, int(option_id), -1 if is_anonymous else session['user_id']))

                if is_anonymous:
                    cursor.execute("UPDATE VoteTokens SET IsUsed = 1 WHERE Token = ?", (hashed_token,))

                conn.commit()
                flash('Your vote has been recorded successfully!', 'success')
            else:
                flash('You have already voted in this poll.', 'info')

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


    @student_bp.route('/poll/<int:poll_id>/results')
    @login_required
    def view_poll_results(poll_id):
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.view_polls'))

        try:
            cursor = conn.cursor()

            # Check if user is moderator
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCARole = 'moderator'
            """, (session['user_id'],))
            user_is_moderator = cursor.fetchone()[0] > 0

            # Get poll details
            cursor.execute("""
                SELECT p.PollId, p.Question, p.QuestionType, p.StartDate, p.EndDate, 
                    p.IsAnonymous, c.Name AS CCAName, p.LiveIsActive
                FROM v_Poll_With_LiveStatus p
                JOIN CCA c ON p.CCAId = c.CCAId
                WHERE p.PollId = ?
            """, (poll_id,))
            poll_data_row = cursor.fetchone()

            if not poll_data_row:
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.view_polls'))

            # Check if user is member of the CCA
            cursor.execute("""
                SELECT COUNT(*)
                FROM CCAMembers cm
                JOIN Poll p ON cm.CCAId = p.CCAId
                WHERE cm.UserId = ? AND p.PollId = ?
            """, (session['user_id'], poll_id))
            is_member_of_cca = cursor.fetchone()[0] > 0

            if not is_member_of_cca and session['role'] != 'admin':
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.view_polls'))

            # Create poll object
            start_date_obj = poll_data_row[3]
            end_date_obj = poll_data_row[4]
            start_date_str = start_date_obj.strftime('%Y-%m-%d %H:%M') if isinstance(start_date_obj, datetime) else str(start_date_obj) if start_date_obj else 'N/A'
            end_date_str = end_date_obj.strftime('%Y-%m-%d %H:%M') if isinstance(end_date_obj, datetime) else str(end_date_obj) if end_date_obj else 'N/A'
            
            poll = {
                'PollId': poll_data_row[0], 
                'Question': poll_data_row[1], 
                'QuestionType': poll_data_row[2],
                'StartDate': convert_utc_to_gmt8_display(poll_data_row[3]),
                'EndDate': convert_utc_to_gmt8_display(poll_data_row[4]),
                'IsAnonymous': poll_data_row[5],
                'CCAName': poll_data_row[6], 
                'LiveIsActive': poll_data_row[7]
            }

            # Get options with vote counts
            cursor.execute("""
                SELECT o.OptionId, o.OptionText, COUNT(v.VoteId) AS VoteCount
                FROM Options o
                LEFT JOIN Votes v ON o.OptionId = v.OptionId
                WHERE o.PollId = ?
                GROUP BY o.OptionId, o.OptionText
                ORDER BY COUNT(v.VoteId) DESC, o.OptionId
            """, (poll_id,))
            options_data = cursor.fetchall()

            # Calculate total votes and percentages
            total_votes = sum(opt[2] for opt in options_data)
            options = []
            for opt in options_data:
                percentage = (opt[2] / total_votes * 100) if total_votes > 0 else 0
                options.append({
                    'OptionId': opt[0], 
                    'OptionText': opt[1], 
                    'VoteCount': opt[2],
                    'Percentage': round(percentage, 1)
                })

            # Get total number of eligible voters (CCA members)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM CCAMembers cm 
                JOIN Poll p ON cm.CCAId = p.CCAId 
                WHERE p.PollId = ?
            """, (poll_id,))
            total_eligible_voters = cursor.fetchone()[0]

            # Calculate participation rate
            participation_rate = (total_votes / total_eligible_voters * 100) if total_eligible_voters > 0 else 0

            # Check if current user voted (if not anonymous)
            user_voted = False
            user_votes = []
            if not poll['IsAnonymous']:
                cursor.execute("SELECT COUNT(*) FROM Votes WHERE PollId = ? AND UserId = ?", (poll_id, session['user_id']))
                user_voted = cursor.fetchone()[0] > 0
                
                if user_voted:
                    cursor.execute("SELECT OptionId FROM Votes WHERE PollId = ? AND UserId = ?", (poll_id, session['user_id']))
                    user_votes_data = cursor.fetchall()
                    user_votes = [uv[0] for uv in user_votes_data]

            return render_template('view_result.html', 
                                poll=poll, 
                                options=options, 
                                total_votes=total_votes,
                                total_eligible_voters=total_eligible_voters,
                                participation_rate=round(participation_rate, 1),
                                user_voted=user_voted,
                                user_votes=user_votes,
                                user_name=session.get('name'),
                                user_is_moderator=user_is_moderator)
            
        except Exception as e:
            print(f"Error fetching poll results for poll {poll_id}: {e}")
            flash('Error fetching poll results.', 'error')
            return redirect(url_for('student_routes.view_polls'))
        finally:
            if conn:
                conn.close()
    
    @student_bp.route('/cca/<int:cca_id>')
    @login_required
    def student_view_cca(cca_id):
        if session.get('role') == 'admin':
            return redirect(url_for('admin_routes.admin_dashboard'))
        
        """View-only CCA page for normal students (non-moderators)"""
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.my_ccas'))
        
        try:
            cursor = conn.cursor()
            
            # Check if user is moderator - ADD THIS BLOCK
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCARole = 'moderator'
            """, (session['user_id'],))
            user_is_moderator = cursor.fetchone()[0] > 0
            
            # Check if user is a member of this CCA
            cursor.execute("""
                SELECT cm.CCARole 
                FROM CCAMembers cm 
                WHERE cm.UserId = ? AND cm.CCAId = ?
            """, (session['user_id'], cca_id))
            membership = cursor.fetchone()
            
            if not membership:
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            # Get CCA details
            cursor.execute("SELECT CCAId, Name, Description FROM CCA WHERE CCAId = ?", (cca_id,))
            cca = cursor.fetchone()
            
            if not cca:
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.my_ccas'))
            
            # Get CCA members
            members_query = """
            SELECT s.StudentId, s.Name, s.Email, cm.CCARole, cm.MemberId
            FROM CCAMembers cm
            INNER JOIN v_ActiveUserDetails ud ON cm.UserId = ud.UserId
            INNER JOIN v_ActiveStudents s ON ud.StudentId = s.StudentId
            WHERE cm.CCAId = ?
            ORDER BY cm.CCARole DESC, s.Name
            """
            cursor.execute(members_query, (cca_id,))
            members = cursor.fetchall()
            
            return render_template('student_view_cca.html', 
                                cca=cca, 
                                members=members,
                                user_name=session['name'],
                                user_is_moderator=user_is_moderator)  # ADD THIS LINE
            
        except Exception as e:
            print(f"Error fetching poll details for poll {cca_id}: {e}")
            flash('Error fetching poll details.', 'error')
            return redirect(url_for('student_routes.view_polls'))
        finally:
            if conn:
                conn.close()

    @student_bp.route('/change-password', methods=['GET', 'POST'])
    @login_required
    def change_password():
        # Helper function to check if user is moderator
        def get_moderator_status():
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT COUNT(*) FROM CCAMembers 
                        WHERE UserId = ? AND CCARole = 'moderator'
                    """, (session['user_id'],))
                    return cursor.fetchone()[0] > 0
                except:
                    return False
                finally:
                    conn.close()
            return False

        if request.method == 'POST':
            current_password = request.form.get('current_password', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            # Get moderator status for all error returns
            user_is_moderator = get_moderator_status()
            
            # Basic validation
            if not all([current_password, new_password, confirm_password]):
                flash('All fields are required.', 'error')
                return render_template('change_password.html', 
                                    user_name=session['name'],
                                    user_is_moderator=user_is_moderator)
            
            if new_password != confirm_password:
                flash('New passwords do not match.', 'error')
                return render_template('change_password.html',
                                    user_name=session['name'],
                                    user_is_moderator=user_is_moderator)
            
            is_valid, errors = validate_password_nist(new_password)
            if not is_valid:
                for error in errors:
                    flash(error, 'error')
                return render_template('change_password.html',
                                    user_name=session['name'],
                                    user_is_moderator=user_is_moderator)
            
            conn = get_db_connection()
            if not conn:
                flash('Database connection error.', 'error')
                return render_template('change_password.html',
                                    user_name=session['name'],
                                    user_is_moderator=user_is_moderator)
            
            try:
                cursor = conn.cursor()
                
                # Get current password
                cursor.execute("SELECT Password FROM UserDetails WHERE UserId = ?", (session['user_id'],))
                stored_password_row = cursor.fetchone()
                
                if not stored_password_row:
                    flash('User not found.', 'error')
                    return render_template('change_password.html',
                                        user_name=session['name'],
                                        user_is_moderator=user_is_moderator)
                
                stored_password = stored_password_row[0]
                
                # Verify current password 
                if not bcrypt.checkpw(current_password.encode('utf-8'), stored_password.encode('utf-8')):
                    flash('Current password is incorrect.', 'error')
                    return render_template('change_password.html',
                                        user_name=session['name'],
                                        user_is_moderator=user_is_moderator)
                
                # Update password in database 
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cursor.execute("""
                    UPDATE UserDetails 
                    SET Password = ? 
                    WHERE UserId = ?
                """, (hashed_password, session['user_id']))
                
                conn.commit()
                
                flash('Password changed successfully!', 'success')
                return redirect(url_for('student_routes.dashboard'))
                
            except Exception as e:
                if conn:
                    conn.rollback()
                print(f"Password change error: {e}")
                flash('Error changing password. Please try again.', 'error')
                return render_template('change_password.html',
                                    user_name=session['name'],
                                    user_is_moderator=user_is_moderator)
            finally:
                if conn:
                    conn.close()
        
        # GET request - check if user is moderator and pass to template
        user_is_moderator = get_moderator_status()
        return render_template('change_password.html', 
                            user_name=session['name'],
                            user_is_moderator=user_is_moderator)
    

    app.register_blueprint(student_bp) # Add this line to register the blueprint
