import os
from dotenv import load_dotenv
from flask import Flask, request, render_template, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# Load environment variables from .env file
load_dotenv()

# Get API key and admin credentials from environment variables
api_key = os.getenv("ANTHROPIC_API_KEY")
admin_username = os.getenv("ADMIN_USERNAME")
admin_password = os.getenv("ADMIN_PASSWORD")

# Initialize the Anthropics client
import anthropic
client = anthropic.Anthropic(api_key=api_key)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pacerclub.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

# Conversation model
class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
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
        "- Suggest reaching out to the support team at [support@pacer.org.cn](mailto:support@pacer.org.cn) or the team leader [Zigao Wang](mailto:a@zigao.wang) for further assistance."
    )

@app.route('/')
@login_required
def index():
    conversations = Conversation.query.filter_by(user_id=current_user.id).all()
    return render_template('index.html', conversations=conversations, username=current_user.username)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('system_message', None)  # Clear the system message from the session on logout
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        if 'add_user' in request.form:
            username = request.form['username']
            password = request.form['password']
            if User.query.filter_by(username=username).first():
                flash('User already exists', 'danger')
            else:
                new_user = User(username=username, password=password)
                db.session.add(new_user)
                db.session.commit()
                flash('User added successfully', 'success')
        elif 'reset_password' in request.form:
            user_id = request.form['user_id']
            new_password = request.form['new_password']
            user = User.query.get(user_id)
            if user:
                user.password = new_password
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

def handle_conversation(user_query, user_id=None):
    # Retrieve existing conversation history from the database
    if user_id:
        conversation_history = Conversation.query.filter_by(user_id=user_id).all()
    else:
        conversation_history = []

    # Create a list of dictionaries with alternating roles
    conversation_dicts = [{"role": convo.role, "content": convo.content} for convo in conversation_history]

    # Ensure roles alternate correctly
    if conversation_dicts and conversation_dicts[-1]["role"] == "user":
        conversation_dicts.pop()  # Remove the last user message if it exists without an assistant response

    # Check if this is the first message in the session
    if 'system_message' not in session:
        system_message = generate_system_message()
        session['system_message'] = system_message  # Store the system message in the session
    else:
        system_message = session['system_message']

    # Append the new user message
    conversation_dicts.append({"role": "user", "content": user_query})

    def generate():
        print(f"Conversation Dicts: {conversation_dicts}")  # Print the conversation_dicts for debugging
        print(f"System Message: {system_message}")  # Print the system_message for debugging
        try:
            with client.messages.stream(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=4000,
                    temperature=0,
                    system=system_message,  # Pass the system_message as a top-level parameter
                    messages=conversation_dicts
            ) as stream:
                for text in stream.text_stream:
                    yield f"{text}"

            # Append AI response to conversation history
            final_message = stream.get_final_message()
            ai_response_content = ''.join(block.text for block in final_message.content)
            ai_response = {"role": "assistant", "content": ai_response_content.strip()}
            conversation_dicts.append(ai_response)

            # Save the updated conversation history to the database
            if user_id:
                with app.app_context():
                    # Save only the new user message and AI response
                    db.session.add(Conversation(user_id=user_id, role="user", content=user_query))
                    db.session.add(Conversation(user_id=user_id, role="assistant", content=ai_response_content.strip()))
                    db.session.commit()
        except Exception as e:
            print(f"Exception in generate: {e}")

    return Response(generate(), content_type='text/event-stream')

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_query = request.json.get('message')
    response_text = handle_conversation(user_query, current_user.id)
    return response_text

@app.route('/guest_chat', methods=['POST'])
def guest_chat():
    user_query = request.json.get('message')
    response_text = handle_conversation(user_query)
    return response_text

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username=admin_username).first():
            db.session.add(User(username=admin_username, password=admin_password, is_admin=True))
            db.session.commit()
    app.run(debug=True)