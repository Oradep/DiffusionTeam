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

# --- Конфигурация ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-777')

# Исправление URL для SQLAlchemy (Postgres на Vercel/Render требует postgresql://)
uri = os.environ.get('DATABASE_URL')
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or 'sqlite:///database.db'
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
    __tablename__ = 'users'  # Переименовали, чтобы не было конфликта в Postgres
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    image_url = db.Column(db.String(500), nullable=True)
    public_id = db.Column(db.String(255), nullable=True)

@login_manager.user_loader
def load_user(user_id):
    # Добавлена проверка, чтобы не падать при ложных сессиях
    return db.session.get(User, int(user_id))

# --- Контекст и фильтры ---
@app.context_processor
def inject_year():
    return {'year': datetime.utcnow().year}

@app.template_filter('datetimeformat')
def format_datetime_filter(value, format='d MMMM yyyy'):
    if value is None: return ""
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
    except:
        team_data = {}
    return render_template('team.html', team_data=team_data, title="Наша команда")

@app.route('/blog')
def blog():
    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('blog.html', posts=posts, title="Блог")

@app.route('/post/<int:post_id>')
def post(post_id):
    post_item = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post_item, title=post_item.title)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('admin'))
        flash('Ошибка входа. Проверьте данные.', 'danger')
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

        img_url = None
        p_id = None

        if image and image.filename != '':
            try:
                upload_result = cloudinary.uploader.upload(image)
                img_url = upload_result.get('secure_url')
                p_id = upload_result.get('public_id')
            except Exception as e:
                flash(f'Ошибка Cloudinary: {e}', 'danger')

        new_post = Post(title=title, content=content, image_url=img_url, public_id=p_id)
        db.session.add(new_post)
        db.session.commit()
        flash('Пост опубликован!', 'success')
        return redirect(url_for('admin'))

    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('admin.html', title="Админ-панель", posts=posts)

@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post_item = Post.query.get_or_404(post_id)
    if post_item.public_id:
        try:
            cloudinary.uploader.destroy(post_item.public_id)
        except:
            pass
    db.session.delete(post_item)
    db.session.commit()
    flash('Пост удален', 'success')
    return redirect(url_for('admin'))

# --- ИНИЦИАЛИЗАЦИЯ (Запустить один раз!) ---
@app.route('/init-db')
def init_db():
    try:
        db.create_all()
        if not User.query.filter_by(username=ADMIN_USERNAME).first():
            hashed_password = generate_password_hash(ADMIN_PASSWORD, method='pbkdf2:sha256')
            admin_user = User(username=ADMIN_USERNAME, password=hashed_password)
            db.session.add(admin_user)
            db.session.commit()
        return "База данных успешно создана и админ добавлен!"
    except Exception as e:
        return f"Ошибка при инициализации: {e}"

if __name__ == '__main__':
    app.run(debug=True)