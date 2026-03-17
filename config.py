# Team Chat - 配置文件
import os
from datetime import timedelta

# 基础配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = os.urandom(24).hex()  # 生产环境应固定

# 数据库
DATABASE_PATH = os.path.join(BASE_DIR, 'team_chat.db')

# 文件上传
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm', 'mov', 'avi'}

# 消息存储
MESSAGE_RETENTION_DAYS = 10

# 会话配置
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

# 管理员用户名密码（首次启动后建议修改）
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'Admin@123'

# Socket.IO 配置
SOCKETIO_ASYNC_MODE = 'threading'
