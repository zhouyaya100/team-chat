# -*- coding: utf-8 -*-
# Team Chat - 主应用
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import uuid
import logging
import mimetypes
import struct


def _check_image_type(header):
    """兼容 Python 3.14+（imghdr 已移除）的图片类型检测"""
    if header[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if header[:2] == b'\xff\xd8':
        return 'jpeg'
    if header[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'webp'
    return None

from config import *
from models import get_db, DatabaseConnection, init_db, cleanup_expired_messages
from auth import hash_password, verify_password, login_required, admin_required, get_current_user

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 初始化 Flask 应用
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PERMANENT_SESSION_LIFETIME'] = PERMANENT_SESSION_LIFETIME

# 初始化 Socket.IO
socketio_cors = os.environ.get('SOCKETIO_CORS_ORIGINS', '*')
if socketio_cors and socketio_cors != '*':
    socketio_cors = [origin.strip() for origin in socketio_cors.split(',')]
socketio = SocketIO(app, async_mode=SOCKETIO_ASYNC_MODE, cors_allowed_origins=socketio_cors)

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==================== 工具函数 ====================

def is_safe_filename(filename):
    """检查文件名是否安全（防止路径遍历）"""
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        return False
    if '..' in filename or '/' in filename or '\\' in filename:
        return False
    return True


def validate_file_mime(file_storage, extension):
    """验证文件 MIME 类型（服务端校验，不信任客户端）"""
    ext = extension.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, '不支持的文件类型'

    header = file_storage.read(1024)
    file_storage.seek(0)

    image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    if ext in image_extensions:
        real_type = _check_image_type(header)
        if real_type not in image_extensions:
            return False, '文件内容与扩展名不匹配'

    return True, None


# ==================== 页面路由 ====================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()

        if user and verify_password(password, user['password_hash']):
            # 修复 Session 固定攻击：清除旧 session 再写入新数据
            old_data = {
                'user_id': user['id'],
                'username': user['username'],
                'nickname': user['nickname'],
                'is_admin': bool(user['is_admin'])
            }
            session.clear()
            session.update(old_data)
            session.permanent = True
            with DatabaseConnection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET status = 'online' WHERE id = ?", (user['id'],))
            return redirect(url_for('chat'))

        return render_template('login.html', error='用户名或密码错误')

    return render_template('login.html')


@app.route('/logout')
def logout():
    if 'user_id' in session:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET status = 'offline' WHERE id = ?", (session['user_id'],))
    session.clear()
    return redirect(url_for('login'))


@app.route('/api/update_profile', methods=['POST'])
@login_required
def update_profile():
    """更新个人资料和密码"""
    user = get_current_user()
    nickname = request.json.get('nickname', '').strip()
    current_password = request.json.get('current_password')
    new_password = request.json.get('new_password')

    if not nickname:
        return jsonify({'error': '昵称不能为空'}), 400

    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET nickname = ? WHERE id = ?", (nickname, user['id']))

        if current_password and new_password:
            cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user['id'],))
            row = cursor.fetchone()
            stored_hash = row['password_hash']

            if not verify_password(current_password, stored_hash):
                return jsonify({'error': '当前密码错误'}), 400

            if len(new_password) < 6:
                return jsonify({'error': '新密码至少 6 个字符'}), 400

            new_hash = hash_password(new_password)
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user['id']))

    session['nickname'] = nickname
    return jsonify({'success': True, 'nickname': nickname if nickname != user['nickname'] else None})


@app.route('/chat')
@login_required
def chat():
    user = get_current_user()
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT g.* FROM groups g
            JOIN group_members gm ON g.id = gm.group_id
            WHERE gm.user_id = ?
            ORDER BY g.created_at DESC
        ''', (user['id'],))
        groups = cursor.fetchall()

        cursor.execute("SELECT id, username, nickname, status FROM users WHERE status = 'online'")
        online_users = cursor.fetchall()

        cursor.execute("SELECT id, username, nickname, status FROM users")
        all_users = cursor.fetchall()

    return render_template('chat.html', user=user, groups=groups, online_users=online_users, users=all_users)


@app.route('/admin')
@login_required
def admin():
    if not session.get('is_admin'):
        return redirect(url_for('chat'))

    user = get_current_user()
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM groups ORDER BY created_at DESC")
        groups = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT id, username, nickname, status, is_admin, created_at FROM users ORDER BY created_at DESC")
        users = [dict(row) for row in cursor.fetchall()]

    return render_template('admin.html', user=user, groups=groups, users=users)


# ==================== API 路由 ====================

@app.route('/api/messages/<int:group_id>', methods=['GET'])
@login_required
def get_messages(group_id):
    """获取群组消息（支持分页）"""
    user = get_current_user()
    before_id = request.args.get('before_id', None, type=int)
    per_page = MESSAGES_PER_PAGE

    with DatabaseConnection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user['id'])
        )
        if not cursor.fetchone():
            return jsonify({'error': '无权访问此群组'}), 403

        if before_id:
            cursor.execute('''
                SELECT m.*, u.username, u.nickname, u.avatar,
                       f.filename, f.original_name, f.file_size, f.mime_type
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                LEFT JOIN files f ON m.file_id = f.id
                WHERE m.group_id = ? AND m.id < ?
                ORDER BY m.created_at DESC LIMIT ?
            ''', (group_id, before_id, per_page))
        else:
            cursor.execute('''
                SELECT m.*, u.username, u.nickname, u.avatar,
                       f.filename, f.original_name, f.file_size, f.mime_type
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                LEFT JOIN files f ON m.file_id = f.id
                WHERE m.group_id = ?
                ORDER BY m.created_at DESC LIMIT ?
            ''', (group_id, per_page))

        messages = []
        for row in cursor.fetchall():
            messages.append({
                'id': row['id'], 'group_id': row['group_id'],
                'sender_id': row['sender_id'], 'username': row['username'],
                'nickname': row['nickname'], 'avatar': row['avatar'],
                'content': row['content'],
                'file': {
                    'id': row['file_id'], 'filename': row['filename'],
                    'original_name': row['original_name'],
                    'file_size': row['file_size'], 'mime_type': row['mime_type']
                } if row['file_id'] else None,
                'created_at': row['created_at']
            })

        cursor.execute("SELECT COUNT(*) as total FROM messages WHERE group_id = ?", (group_id,))
        total = cursor.fetchone()['total']

    messages.reverse()
    return jsonify({'messages': messages, 'has_more': len(messages) >= per_page, 'total': total})


@app.route('/api/files/<int:file_id>')
@login_required
def download_file(file_id):
    """下载文件"""
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        file = cursor.fetchone()

        if not file:
            return jsonify({'error': '文件不存在'}), 404

        if not is_safe_filename(file['filename']):
            logger.error(f"路径遍历攻击: file_id={file_id}, filename={file['filename']}")
            return jsonify({'error': '文件名不合法'}), 400

        file_abs_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, file['filename']))
        upload_abs_path = os.path.abspath(UPLOAD_FOLDER)
        if not file_abs_path.startswith(upload_abs_path):
            logger.error(f"文件路径超出上传目录: {file_abs_path}")
            return jsonify({'error': '文件路径不合法'}), 400

        cursor.execute("UPDATE files SET download_count = download_count + 1 WHERE id = ?", (file_id,))

    return send_from_directory(UPLOAD_FOLDER, file['filename'], as_attachment=True, download_name=file['original_name'])


@app.route('/api/private_messages/<int:user_id>', methods=['GET'])
@login_required
def get_private_messages(user_id):
    """获取私聊消息（支持分页）"""
    current_user = get_current_user()
    before_id = request.args.get('before_id', None, type=int)
    per_page = MESSAGES_PER_PAGE

    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            return jsonify({'error': '用户不存在'}), 404

        if before_id:
            cursor.execute('''
                SELECT pm.*, u.username as sender_username, u.nickname as sender_nickname, u.avatar as sender_avatar,
                       f.filename, f.original_name, f.file_size, f.mime_type
                FROM private_messages pm
                JOIN users u ON pm.sender_id = u.id
                LEFT JOIN files f ON pm.file_id = f.id
                WHERE ((pm.sender_id = ? AND pm.receiver_id = ?) OR (pm.sender_id = ? AND pm.receiver_id = ?))
                       AND pm.id < ?
                ORDER BY pm.created_at DESC LIMIT ?
            ''', (current_user['id'], user_id, user_id, current_user['id'], before_id, per_page))
        else:
            cursor.execute('''
                SELECT pm.*, u.username as sender_username, u.nickname as sender_nickname, u.avatar as sender_avatar,
                       f.filename, f.original_name, f.file_size, f.mime_type
                FROM private_messages pm
                JOIN users u ON pm.sender_id = u.id
                LEFT JOIN files f ON pm.file_id = f.id
                WHERE (pm.sender_id = ? AND pm.receiver_id = ?) OR (pm.sender_id = ? AND pm.receiver_id = ?)
                ORDER BY pm.created_at DESC LIMIT ?
            ''', (current_user['id'], user_id, user_id, current_user['id'], per_page))

        messages = []
        for row in cursor.fetchall():
            messages.append({
                'id': row['id'], 'sender_id': row['sender_id'], 'receiver_id': row['receiver_id'],
                'username': row['sender_username'], 'nickname': row['sender_nickname'],
                'avatar': row['sender_avatar'], 'content': row['content'],
                'file': {
                    'id': row['file_id'], 'filename': row['filename'],
                    'original_name': row['original_name'],
                    'file_size': row['file_size'], 'mime_type': row['mime_type']
                } if row['file_id'] else None,
                'created_at': row['created_at']
            })

        cursor.execute('''
            UPDATE private_messages SET is_read = 1
            WHERE receiver_id = ? AND sender_id = ? AND is_read = 0
        ''', (current_user['id'], user_id))

    messages.reverse()
    return jsonify({'messages': messages, 'has_more': len(messages) >= per_page})


@app.route('/api/unread/count', methods=['GET'])
@login_required
def get_unread_count():
    """获取未读消息数量"""
    user = get_current_user()
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT gm.group_id, COUNT(m.id) as unread_count
            FROM group_members gm
            LEFT JOIN unread_group_messages ugm ON gm.group_id = ugm.group_id AND ugm.user_id = ?
            LEFT JOIN messages m ON m.group_id = gm.group_id
                AND m.created_at > COALESCE(ugm.last_read_at, '1970-01-01') AND m.sender_id != ?
            WHERE gm.user_id = ? GROUP BY gm.group_id
        ''', (user['id'], user['id'], user['id']))

        group_unread = {row['group_id']: row['unread_count'] for row in cursor.fetchall() if row['unread_count'] > 0}

        cursor.execute('''
            SELECT sender_id, COUNT(*) as unread_count FROM private_messages
            WHERE receiver_id = ? AND is_read = 0 GROUP BY sender_id
        ''', (user['id'],))
        private_unread = {row['sender_id']: row['unread_count'] for row in cursor.fetchall() if row['unread_count'] > 0}

    return jsonify({'groups': group_unread, 'private': private_unread})


@app.route('/api/mark_read/group/<int:group_id>', methods=['POST'])
@login_required
def mark_group_read(group_id):
    user = get_current_user()
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(id) as latest_id FROM messages WHERE group_id = ?', (group_id,))
        latest = cursor.fetchone()
        latest_id = latest['latest_id'] if latest and latest['latest_id'] else 0
        cursor.execute('''
            INSERT OR REPLACE INTO unread_group_messages (user_id, group_id, last_read_message_id, last_read_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user['id'], group_id, latest_id))
    return jsonify({'success': True})


@app.route('/api/mark_read/private/<int:user_id>', methods=['POST'])
@login_required
def mark_private_read(user_id):
    current_user = get_current_user()
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT MAX(id) as latest_id FROM private_messages
            WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
        ''', (current_user['id'], user_id, user_id, current_user['id']))
        latest = cursor.fetchone()
        latest_id = latest['latest_id'] if latest and latest['latest_id'] else 0
        cursor.execute('''
            INSERT OR REPLACE INTO unread_private_messages (user_id, sender_id, last_read_message_id, last_read_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (current_user['id'], user_id, latest_id))
        cursor.execute('''
            UPDATE private_messages SET is_read = 1
            WHERE receiver_id = ? AND sender_id = ? AND is_read = 0
        ''', (current_user['id'], user_id))
    return jsonify({'success': True})


@app.route('/api/clear_unread', methods=['POST'])
@login_required
def clear_all_unread():
    user = get_current_user()
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(id) as latest FROM messages')
        latest_group = cursor.fetchone()['latest'] or 0
        cursor.execute('SELECT MAX(id) as latest FROM private_messages')
        latest_private = cursor.fetchone()['latest'] or 0
        cursor.execute('''
            INSERT OR REPLACE INTO unread_group_messages (user_id, group_id, last_read_message_id, last_read_at)
            SELECT ?, group_id, ?, CURRENT_TIMESTAMP FROM group_members WHERE user_id = ?
        ''', (user['id'], latest_group, user['id']))
        cursor.execute('''
            INSERT OR REPLACE INTO unread_private_messages (user_id, sender_id, last_read_message_id, last_read_at)
            SELECT DISTINCT ?, sender_id, ?, CURRENT_TIMESTAMP FROM private_messages WHERE receiver_id = ?
        ''', (user['id'], latest_private, user['id']))
        cursor.execute('UPDATE private_messages SET is_read = 1 WHERE receiver_id = ?', (user['id'],))
    return jsonify({'success': True})


# ==================== Socket.IO 事件 ====================

@socketio.on('join_group')
def on_join_group(data):
    group_id = data['group_id']
    user = get_current_user()
    if not user:
        return {'error': '请先登录'}
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user['id']))
        if not cursor.fetchone():
            return {'error': '无权访问此群组'}
    join_room(f"group_{group_id}")
    logger.info(f"用户 {user['username']} 加入群组 {group_id}")


@socketio.on('leave_group')
def on_leave_group(data):
    group_id = data['group_id']
    leave_room(f"group_{group_id}")


@socketio.on('send_message')
def on_send_message(data):
    if 'user_id' not in session:
        return {'error': '请先登录'}
    group_id = data.get('group_id')
    content = data.get('content', '').strip()
    file_id = data.get('file_id')
    if not content and not file_id:
        return {'error': '消息不能为空'}

    user = get_current_user()
    expires_at = datetime.now() + timedelta(days=MESSAGE_RETENTION_DAYS)

    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        # 🔒 验证用户是否在群组中
        cursor.execute("SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user['id']))
        if not cursor.fetchone():
            return {'error': '无权在此群组发言'}
        cursor.execute('''
            INSERT INTO messages (group_id, sender_id, content, file_id, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (group_id, user['id'], content if content else None, file_id, expires_at))
        message_id = cursor.lastrowid

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.*, u.username, u.nickname, u.avatar,
               f.filename, f.original_name, f.file_size, f.mime_type
        FROM messages m JOIN users u ON m.sender_id = u.id
        LEFT JOIN files f ON m.file_id = f.id WHERE m.id = ?
    ''', (message_id,))
    row = cursor.fetchone()
    conn.close()

    message = {
        'id': row['id'], 'group_id': row['group_id'], 'sender_id': row['sender_id'],
        'username': row['username'], 'nickname': row['nickname'], 'avatar': row['avatar'],
        'content': row['content'],
        'file': {'id': row['file_id'], 'filename': row['filename'],
                 'original_name': row['original_name'], 'file_size': row['file_size'],
                 'mime_type': row['mime_type']} if row['file_id'] else None,
        'created_at': row['created_at']
    }
    emit('new_message', message, room=f"group_{group_id}")
    return {'success': True, 'message_id': message_id}


@socketio.on('join_private')
def on_join_private(data):
    user_id = data['user_id']
    current_user = get_current_user()
    if not current_user:
        return {'error': '请先登录'}
    room_users = sorted([current_user['id'], user_id])
    room_name = f"private_{room_users[0]}_{room_users[1]}"
    join_room(room_name)


@socketio.on('leave_private')
def on_leave_private(data):
    user_id = data['user_id']
    current_user = get_current_user()
    if current_user:
        room_users = sorted([current_user['id'], user_id])
        room_name = f"private_{room_users[0]}_{room_users[1]}"
        leave_room(room_name)


@socketio.on('send_private_message')
def on_send_private_message(data):
    if 'user_id' not in session:
        return {'error': '请先登录'}
    receiver_id = data.get('receiver_id')
    content = data.get('content', '').strip()
    file_id = data.get('file_id')
    if not content and not file_id:
        return {'error': '消息不能为空'}

    user = get_current_user()
    # 🔒 禁止给自己发消息
    if user['id'] == receiver_id:
        return {'error': '不能给自己发消息'}

    expires_at = datetime.now() + timedelta(days=MESSAGE_RETENTION_DAYS)

    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        # 🔒 验证接收者存在
        cursor.execute("SELECT 1 FROM users WHERE id = ?", (receiver_id,))
        if not cursor.fetchone():
            return {'error': '接收用户不存在'}
        cursor.execute('''
            INSERT INTO private_messages (sender_id, receiver_id, content, file_id, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user['id'], receiver_id, content if content else None, file_id, expires_at))
        message_id = cursor.lastrowid

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pm.*, u.username, u.nickname, u.avatar,
               f.filename, f.original_name, f.file_size, f.mime_type
        FROM private_messages pm JOIN users u ON pm.sender_id = u.id
        LEFT JOIN files f ON pm.file_id = f.id WHERE pm.id = ?
    ''', (message_id,))
    row = cursor.fetchone()
    conn.close()

    message = {
        'id': row['id'], 'sender_id': row['sender_id'], 'receiver_id': row['receiver_id'],
        'username': row['username'], 'nickname': row['nickname'], 'avatar': row['avatar'],
        'content': row['content'],
        'file': {'id': row['file_id'], 'filename': row['filename'],
                 'original_name': row['original_name'], 'file_size': row['file_size'],
                 'mime_type': row['mime_type']} if row['file_id'] else None,
        'created_at': row['created_at']
    }
    room_users = sorted([user['id'], receiver_id])
    room_name = f"private_{room_users[0]}_{room_users[1]}"
    emit('new_private_message', message, room=room_name)
    return {'success': True, 'message_id': message_id}


@socketio.on('connect')
def on_connect():
    user = get_current_user()
    if user:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET status = 'online' WHERE id = ?", (user['id'],))
        emit('user_status_change', {'user_id': user['id'], 'status': 'online'}, broadcast=True)


@socketio.on('disconnect')
def on_disconnect():
    user = get_current_user()
    if user:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET status = 'offline' WHERE id = ?", (user['id'],))
        emit('user_status_change', {'user_id': user['id'], 'status': 'offline'}, broadcast=True)


# ==================== 管理员 API ====================

@app.route('/api/admin/create_user', methods=['POST'])
@admin_required
def create_user():
    username = request.json.get('username', '').strip()
    nickname = request.json.get('nickname', '').strip()
    password = request.json.get('password', '')
    is_admin = request.json.get('is_admin', False)

    if not username or not nickname or not password:
        return jsonify({'error': '请填写所有字段'}), 400
    if len(username) < 3:
        return jsonify({'error': '用户名至少 3 个字符'}), 400
    if len(password) < 6:
        return jsonify({'error': '密码至少 6 个字符'}), 400

    password_hash = hash_password(password)
    try:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, nickname, is_admin) VALUES (?, ?, ?, ?)",
                (username, password_hash, nickname, 1 if is_admin else 0)
            )
        return jsonify({'success': True})
    except Exception as e:
        if 'UNIQUE constraint' in str(e):
            return jsonify({'error': '用户名已存在'}), 400
        logger.error(f"创建用户失败: {e}")
        return jsonify({'error': '创建用户失败'}), 500


@app.route('/api/admin/delete_user/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """删除用户"""
    current_user = get_current_user()
    if user_id == current_user['id']:
        return jsonify({'error': '不能删除自己'}), 400

    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            return jsonify({'error': '用户不存在'}), 404
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return jsonify({'success': True})


@app.route('/api/group_members/<int:group_id>', methods=['GET'])
@login_required
def get_group_members_public(group_id):
    user = get_current_user()
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user['id']))
        if not cursor.fetchone():
            return jsonify({'error': '无权访问此群组'}), 403
        cursor.execute('''
            SELECT u.id, u.username, u.nickname, gm.role, gm.joined_at, u.status
            FROM group_members gm JOIN users u ON gm.user_id = u.id
            WHERE gm.group_id = ? ORDER BY gm.joined_at ASC
        ''', (group_id,))
        members = []
        for row in cursor.fetchall():
            member = dict(row)
            if not member['nickname']:
                member['nickname'] = member['username']
            members.append(member)
    return jsonify(members)


@app.route('/api/admin/group_members/<int:group_id>', methods=['GET'])
@admin_required
def get_group_members_admin(group_id):
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.id, u.username, u.nickname, gm.role, gm.joined_at, u.status
            FROM group_members gm JOIN users u ON gm.user_id = u.id
            WHERE gm.group_id = ? ORDER BY gm.joined_at ASC
        ''', (group_id,))
        members = []
        for row in cursor.fetchall():
            member = dict(row)
            if not member['nickname']:
                member['nickname'] = member['username']
            members.append(member)
    return jsonify(members)


@app.route('/api/admin/user_groups/<int:user_id>', methods=['GET'])
@admin_required
def get_user_groups(user_id):
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT g.id, g.name, g.description FROM groups g
            JOIN group_members gm ON g.id = gm.group_id
            WHERE gm.user_id = ? ORDER BY g.created_at DESC
        ''', (user_id,))
        groups = [dict(row) for row in cursor.fetchall()]
    return jsonify(groups)


@app.route('/api/admin/create_group', methods=['POST'])
@admin_required
def create_group():
    """创建群组（创建者自动加入为 admin）"""
    name = request.json.get('name', '').strip()
    description = request.json.get('description', '').strip()
    if not name:
        return jsonify({'error': '群组名称不能为空'}), 400

    user = get_current_user()
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO groups (name, description, created_by) VALUES (?, ?, ?)",
                       (name, description, user['id']))
        group_id = cursor.lastrowid
        # 创建者自动加入群组，角色为 admin
        cursor.execute("INSERT INTO group_members (group_id, user_id, role) VALUES (?, ?, 'admin')",
                       (group_id, user['id']))
    return jsonify({'success': True, 'group_id': group_id})


@app.route('/api/admin/add_member', methods=['POST'])
@admin_required
def add_member():
    group_id = request.json.get('group_id')
    user_id = request.json.get('user_id')
    if not group_id or not user_id:
        return jsonify({'error': '参数错误'}), 400
    try:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, user_id))
        return jsonify({'success': True})
    except Exception as e:
        if 'UNIQUE constraint' in str(e):
            return jsonify({'error': '用户已在群组中'}), 400
        logger.error(f"添加成员失败: {e}")
        return jsonify({'error': '添加成员失败'}), 500


@app.route('/api/admin/remove_member', methods=['POST'])
@admin_required
def remove_member():
    group_id = request.json.get('group_id')
    user_id = request.json.get('user_id')
    if not group_id or not user_id:
        return jsonify({'error': '参数错误'}), 400
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))
    return jsonify({'success': True})


@app.route('/api/admin/delete_group', methods=['POST'])
@admin_required
def delete_group():
    group_id = request.json.get('group_id')
    if not group_id:
        return jsonify({'error': '参数错误'}), 400
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    return jsonify({'success': True})


# ==================== 文件上传 ====================

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的文件类型: .{ext}'}), 400

    # 🔒 服务端 MIME 验证
    is_valid, mime_error = validate_file_mime(file, ext)
    if not is_valid:
        logger.warning(f"文件 MIME 校验失败: {file.filename}, 原因: {mime_error}")
        return jsonify({'error': mime_error}), 400

    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(file_path)
    file_size = os.path.getsize(file_path)

    mime_type = mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'

    user = get_current_user()
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO files (filename, original_name, file_path, file_size, mime_type, uploaded_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (unique_filename, file.filename, file_path, file_size, mime_type, user['id']))
        file_id = cursor.lastrowid

    return jsonify({
        'success': True, 'file_id': file_id,
        'filename': file.filename, 'file_size': file_size, 'mime_type': mime_type
    })


# ==================== 定时清理（APScheduler）====================

def start_cleanup_scheduler():
    """使用 APScheduler 启动定时清理任务"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(cleanup_expired_messages, 'cron', hour=2, minute=0, id='cleanup')
        scheduler.start()
        logger.info("定时清理任务已启动（每天凌晨 2 点，APScheduler）")
    except ImportError:
        # APScheduler 未安装，降级为线程轮询
        import threading
        import time

        def cleanup_loop():
            last_date = None
            while True:
                now = datetime.now()
                today = now.date()
                if now.hour == 2 and now.minute == 0 and today != last_date:
                    cleanup_expired_messages()
                    last_date = today
                time.sleep(30)

        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
        logger.info("定时清理任务已启动（每天凌晨 2 点，线程降级模式）")


# ==================== 应用启动 ====================

if __name__ == '__main__':
    init_db()

    # 创建默认管理员
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE username = ?", (ADMIN_USERNAME,))
        if not cursor.fetchone():
            password_hash = hash_password(ADMIN_PASSWORD)
            cursor.execute(
                "INSERT INTO users (username, password_hash, nickname, is_admin) VALUES (?, ?, ?, ?)",
                (ADMIN_USERNAME, password_hash, '管理员', 1)
            )
            logger.info(f"默认管理员已创建: {ADMIN_USERNAME}")

    start_cleanup_scheduler()

    logger.info("Team Chat 启动中...")
    logger.info("访问地址: http://127.0.0.1:5001")

    socketio.run(app, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True)
