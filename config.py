# Team Chat - 配置文件
import os
from datetime import timedelta
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()

# 基础配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24).hex())  # 生产环境应设置环境变量

# 数据库
DATABASE_PATH = os.path.join(BASE_DIR, 'team_chat.db')

# 文件上传
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm', 'mov', 'avi'}

# MIME 类型白名单（与 ALLOWED_EXTENSIONS 对应）
ALLOWED_MIME_TYPES = {
    'image/png', 'image/jpeg', 'image/gif', 'image/webp',
    'video/mp4', 'video/webm', 'video/quicktime', 'video/x-msvideo'
}

# 消息存储
MESSAGE_RETENTION_DAYS = 10

# 消息分页
MESSAGES_PER_PAGE = 50

# 会话配置
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

# 管理员用户名密码（优先从环境变量读取）
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin@123')  # ⚠️ 生产环境务必修改！

# Socket.IO 配置
SOCKETIO_ASYNC_MODE = 'threading'
