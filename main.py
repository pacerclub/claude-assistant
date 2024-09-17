import os
from dotenv import load_dotenv
from flask import Flask, request, render_template, redirect, url_for, flash, session, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from sqlalchemy.orm import relationship
import bleach
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message as FlaskMessage
import anthropic
import logging

# Load environment variables from .env file
load_dotenv()

# Get API key and admin credentials from environment variables
api_key = os.getenv("ANTHROPIC_API_KEY")
admin_username = os.getenv("ADMIN_USERNAME")
admin_password = os.getenv("ADMIN_PASSWORD")
admin_email = os.getenv("ADMIN_EMAIL")

# Initialize the Anthropics client
client = anthropic.Anthropic(api_key=api_key)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pacerclub.db'
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT'))
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
mail = Mail(app)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Set up logging
logging.basicConfig(level=logging.INFO)


# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    conversations = relationship('Conversation', back_populates='user', cascade='all, delete-orphan')


# Conversation model
class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = relationship('User', back_populates='conversations')
    messages = relationship('Message', back_populates='conversation', cascade='all, delete-orphan')


# Message model
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    conversation = relationship('Conversation', back_populates='messages')
    role = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Function to generate system message
def generate_system_message():
    return (
        "You are an AI assistant for Pacer Club, a Hack Club initiative founded by Zigao Wang. "
        "Your primary goal is to provide efficient and supportive assistance to Pacer Club members on various tasks related "
        "to coding, design, project ideas, and more. Always be precise, helpful, and offer valuable resources when appropriate.\n\n"
        "When responding to the query, follow these guidelines:\n\n"
        "1. Be concise and precise in your answers.\n"
        "2. Provide helpful information directly related to the query.\n"
        "3. Avoid irrelevant information or unnecessary elaboration.\n"
        "4. Use Markdown formatting for links and code snippets when appropriate.\n\n"
        "Depending on the type of query, follow these specific instructions:\n\n"
        "- For coding questions:\n"
        "  - Provide clear explanations and, if applicable, code snippets.\n"
        "  - Suggest relevant documentation or learning resources.\n\n"
        "- For design-related queries:\n"
        "  - Offer design principles and best practices.\n"
        "  - Recommend tools or resources that could be helpful.\n\n"
        "- For project ideas:\n"
        "  - Suggest innovative and feasible project concepts.\n"
        "  - Provide a brief outline of how to approach the project.\n\n"
        "- For general Pacer Club information:\n"
        "  - Share accurate information about the club's activities and goals.\n"
        "  - Direct members to official resources when appropriate.\n\n"
        "Always aim to encourage community involvement and collaboration. When relevant, include one or more of the following engagement prompts:\n\n"
        "- Encourage members to contribute to the [GitHub repository](https://github.com/pacerclub) for open-source collaboration.\n"
        "- Promote the [official website](https://pacer.org.cn) for events and activities.\n"
        "- Suggest reaching out to the support team at [support@pacer.org.cn](mailto:support@pacer.org.cn) or the team leader [Zigao Wang](mailto:a@zigao.wang) for further assistance.\n"
        "Here are some resources you might need:\n"
        "When the user is asking for logos of Pacer Club, use markdown to show the image URL: https://pacer.org.cn/logo.png"
    )


@app.route('/')
@login_required
def index():
    conversations = Conversation.query.filter_by(user_id=current_user.id).order_by(Conversation.id.desc()).all()
    return render_template('index.html', conversations=conversations, username=current_user.username)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form.get('username_or_email')
        password = request.form.get('password')
        user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email)).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Login Unsuccessful. Please check your credentials.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('system_message', None)  # Clear the system message from the session on logout
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter((User.username == username) | (User.email == email)).first()
        if user:
            flash('Username or email already exists', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        identifier = request.form['identifier']
        user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()

        if user:
            token = s.dumps(user.email, salt='password-reset-salt')
            reset_url = url_for('reset_password_token', token=token, _external=True)

            html_body = render_template('reset_password_email.html',
                                        reset_url=reset_url,
                                        username=user.username)

            try:
                msg = FlaskMessage(subject='Pacer Club - Password Reset Request',
                                   recipients=[user.email],
                                   html=html_body)
                mail.send(msg)
                app.logger.info(f"Password reset email sent to {user.email}")
                flash('An email has been sent with instructions to reset your password.', 'info')
            except Exception as e:
                app.logger.error(f"Failed to send password reset email to {user.email}. Error: {str(e)}")
                flash('An error occurred while sending the email. Please try again later.', 'danger')
        else:
            flash('No account found with that username or email.', 'danger')

        return redirect(url_for('login'))

    return render_template('reset_password.html')


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=3600)
    except:
        flash('The password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('No user found with that email.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_password = request.form['password']
        user.password = generate_password_hash(new_password)
        db.session.commit()
        flash('Your password has been updated! You can now log in with your new password.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password_token.html')


@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        if 'add_user' in request.form:
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            if User.query.filter((User.username == username) | (User.email == email)).first():
                flash('User already exists', 'danger')
            else:
                new_user = User(username=username, email=email, password=generate_password_hash(password))
                db.session.add(new_user)
                db.session.commit()
                flash('User added successfully', 'success')
        elif 'reset_password' in request.form:
            user_id = request.form['user_id']
            new_password = request.form['new_password']
            user = User.query.get(user_id)
            if user:
                user.password = generate_password_hash(new_password)
                db.session.commit()
                flash('Password reset successfully', 'success')
            else:
                flash('User not found', 'danger')
        elif 'delete_user' in request.form:
            user_id = request.form['user_id']
            user = User.query.get(user_id)
            if user:
                db.session.delete(user)
                db.session.commit()
                flash('User deleted successfully', 'success')
            else:
                flash('User not found', 'danger')

    users = User.query.all()
    return render_template('admin.html', users=users)


@app.route('/new_conversation', methods=['POST'])
@login_required
def new_conversation():
    title = request.form.get('title', 'New Conversation')
    conversation = Conversation(title=title, user_id=current_user.id)
    db.session.add(conversation)
    db.session.commit()
    return jsonify({'id': conversation.id, 'title': conversation.title})


@app.route('/get_conversation/<int:conversation_id>', methods=['GET'])
@login_required
def get_conversation(conversation_id):
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first()
    if not conversation:
        return jsonify({'error': 'Invalid conversation'}), 400

    messages = Message.query.filter_by(conversation_id=conversation_id).all()
    messages_data = [{'role': msg.role, 'content': msg.content, 'id': msg.id} for msg in messages]
    return jsonify({'messages': messages_data})


def handle_conversation(user_query, conversation):
    conversation_history = Message.query.filter_by(conversation_id=conversation.id).all()
    conversation_dicts = [{"role": msg.role, "content": msg.content} for msg in conversation_history]

    if 'system_message' not in session:
        system_message = generate_system_message()
        session['system_message'] = system_message
    else:
        system_message = session['system_message']

    conversation_dicts.append({"role": "user", "content": user_query})

    def generate():
        try:
            with client.messages.stream(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=4096,
                    temperature=0,
                    system=system_message,
                    messages=conversation_dicts
            ) as stream:
                for text in stream.text_stream:
                    yield f"{text}"

            final_message = stream.get_final_message()
            ai_response_content = ''.join(block.text for block in final_message.content)
            ai_response = {"role": "assistant", "content": ai_response_content.strip()}
            conversation_dicts.append(ai_response)

            with app.app_context():
                db.session.add(Message(conversation_id=conversation.id, role="user", content=user_query))
                db.session.add(
                    Message(conversation_id=conversation.id, role="assistant", content=ai_response_content.strip()))
                db.session.commit()
        except Exception as e:
            app.logger.error(f"Exception in generate: {e}")

    return Response(generate(), content_type='text/event-stream')


@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_query = request.json.get('message')
    conversation_id = request.json.get('conversation_id')
    conversation = Conversation.query.get(conversation_id)

    if not conversation or conversation.user_id != current_user.id:
        return jsonify({'error': 'Invalid conversation'}), 400

    response_text = handle_conversation(user_query, conversation)
    return response_text


@app.route('/delete_conversation/<int:conversation_id>', methods=['DELETE'])
@login_required
def delete_conversation(conversation_id):
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first()
    if conversation:
        db.session.delete(conversation)
        db.session.commit()
        return jsonify({'success': True}), 200
    return jsonify({'success': False, 'error': 'Conversation not found'}), 404


@app.route('/update_conversation_title/<int:conversation_id>', methods=['POST'])
@login_required
def update_conversation_title(conversation_id):
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first()
    if not conversation:
        return jsonify({'success': False, 'error': 'Conversation not found'}), 404

    new_title = request.json.get('title')
    if not new_title:
        return jsonify({'success': False, 'error': 'No title provided'}), 400

    conversation.title = bleach.clean(new_title)  # Sanitize the input
    db.session.commit()
    return jsonify({'success': True}), 200

class EmailLogger(object):
    def __init__(self, app):
        self.app = app

    def __enter__(self):
        self.original_send = FlaskMessage.send
        FlaskMessage.send = self.logged_send
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        FlaskMessage.send = self.original_send

    def logged_send(self, message):
        self.app.logger.info(f"Sending email to: {message.recipients}")
        self.app.logger.info(f"Email subject: {message.subject}")
        self.app.logger.info(f"Email body: {message.html}")
        return self.original_send(message)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username=admin_username).first():
            db.session.add(User(username=admin_username,
                                email=admin_email,
                                password=generate_password_hash(admin_password),
                                is_admin=True))
            db.session.commit()
    app.run(debug=True, port=1234)