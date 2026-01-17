import os
import json
import cloudinary
import cloudinary.uploader
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_babel import Babel, format_date
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- Конфигурация приложения ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key-123')

# Настройка БД (исправляем протокол для SQLAlchemy)
uri = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['BABEL_DEFAULT_LOCALE'] = 'ru'

# Настройка Cloudinary
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
)

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'pivo3228')

# --- Инициализация ---
db = SQLAlchemy(app)
babel = Babel(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

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
    # Теперь здесь хранится полный URL из Cloudinary
    image_url = db.Column(db.String(500), nullable=True)
    public_id = db.Column(db.String(255), nullable=True) # Для удаления из облака

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Фильтры и контекст ---
@app.context_processor
def inject_year():
    return {'year': datetime.utcnow().year}

@app.template_filter('datetimeformat')
def format_datetime_filter(value, format='d MMMM yyyy'):
    return format_date(value, format)

# --- Маршруты ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/team')
def team():
    try:
        json_path = os.path.join(app.root_path, 'instance', 'members.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            team_data = json.load(f)
    except Exception:
        team_data = {}
    return render_template('team.html', team_data=team_data)

@app.route('/blog')
def blog():
    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('blog.html', posts=posts)

# ДОБАВЛЕН ПРОПУЩЕННЫЙ МАРШРУТ ПРОСМОТРА ПОСТА
@app.route('/post/<int:post_id>')
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('admin'))
        flash('Неверный вход', 'danger')
    return render_template('login.html')

# ДОБАВЛЕН ПРОПУЩЕННЫЙ МАРШРУТ ВЫХОДА
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

        img_url = None
        p_id = None

        if image and image.filename != '':
            try:
                # Загрузка напрямую в Cloudinary
                upload_result = cloudinary.uploader.upload(image)
                img_url = upload_result.get('secure_url')
                p_id = upload_result.get('public_id')
            except Exception as e:
                flash(f'Ошибка загрузки изображения: {e}', 'danger')

        new_post = Post(title=title, content=content, image_url=img_url, public_id=p_id)
        db.session.add(new_post)
        db.session.commit()
        flash('Пост создан!', 'success')
        return redirect(url_for('admin'))

    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('admin.html', posts=posts)

@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.public_id:
        try:
            cloudinary.uploader.destroy(post.public_id)
        except Exception as e:
            print(f"Error deleting from Cloudinary: {e}")
            
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('admin'))

# Маршрут для первичного создания таблиц
@app.route('/init-db')
def init_db():
    db.create_all()
    if not User.query.filter_by(username=ADMIN_USERNAME).first():
        hashed_password = generate_password_hash(ADMIN_PASSWORD, method='pbkdf2:sha256')
        admin_user = User(username=ADMIN_USERNAME, password=hashed_password)
        db.session.add(admin_user)
        db.session.commit()
    return "DB Initialized!"

if __name__ == '__main__':
    app.run(debug=True)