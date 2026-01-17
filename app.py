import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from flask_babel import Babel, format_date
import json
import os
from dotenv import load_dotenv # Добавить это

load_dotenv()

# --- Конфигурация приложения через переменные окружения ---
app = Flask(__name__)

# Секретный ключ (обязательно измените его в настройках хостинга!)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key-123')

# База данных (если переменная не задана, используем sqlite локально)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')

# Папка для загрузки (лучше использовать абсолютный путь)
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', os.path.join(app.root_path, 'static/uploads'))

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['BABEL_DEFAULT_LOCALE'] = 'ru'

# Данные администратора по умолчанию
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'pivo3228')

# --- Инициализация расширений ---
db = SQLAlchemy(app)
babel = Babel(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Пожалуйста, войдите, чтобы получить доступ к этой странице."
login_manager.login_message_category = "info"

# --- Context Processor ---
@app.context_processor
def inject_year():
    return {'year': datetime.utcnow().year}

# --- Custom filter ---
@app.template_filter('datetimeformat')
def format_datetime_filter(value, format='d MMMM yyyy'):
    return format_date(value, format)

# --- Модели ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    image_file = db.Column(db.String(255), nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Маршруты (логика осталась прежней) ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/team')
def team():
    try:
        # Путь к JSON теперь тоже можно настраивать, если нужно
        json_path = os.path.join(app.root_path, 'instance', 'members.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            team_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        team_data = {}
        print("Ошибка: Файл members.json не найден.")
    return render_template('team.html', team_data=team_data, title="Наша команда")

@app.route('/blog')
def blog():
    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('blog.html', posts=posts, title="Блог")

@app.route('/post/<int:post_id>')
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post, title=post.title)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('admin'))
        else:
            flash('Неверный логин или пароль.', 'danger')
    return render_template('login.html', title="Вход")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        image = request.files.get('image')

        if not title or not content:
            flash('Заголовок и содержание не могут быть пустыми.', 'warning')
            return redirect(request.url)
        
        if len(title) > 80:
            flash('Заголовок слишком длинный.', 'warning')
            return redirect(request.url)

        filename = None
        if image and image.filename != '':
            filename = secure_filename(image.filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        new_post = Post(title=title, content=content, image_file=filename)
        db.session.add(new_post)
        db.session.commit()
        flash('Пост успешно создан!', 'success')
        return redirect(url_for('admin'))

    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('admin.html', title="Админ-панель", posts=posts)

@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post_to_delete = Post.query.get_or_404(post_id)
    if post_to_delete.image_file:
        try:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], post_to_delete.image_file)
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            print(f"Ошибка удаления файла: {e}")
    db.session.delete(post_to_delete)
    db.session.commit()
    flash('Пост успешно удален!', 'success')
    return redirect(url_for('admin'))

def setup_database(app):
    with app.app_context():
        db.create_all()
        # Проверяем админа, используя переменные ADMIN_USERNAME и ADMIN_PASSWORD
        if not User.query.filter_by(username=ADMIN_USERNAME).first():
            hashed_password = generate_password_hash(ADMIN_PASSWORD, method='pbkdf2:sha256')
            admin_user = User(username=ADMIN_USERNAME, password=hashed_password)
            db.session.add(admin_user)
            db.session.commit()
            print(f"Администратор '{ADMIN_USERNAME}' создан.")

if __name__ == '__main__':
    setup_database(app)
    # Динамический порт для хостинга
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=os.environ.get('DEBUG', 'False') == 'True', host='0.0.0.0', port=port)