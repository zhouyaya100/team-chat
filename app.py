# -*- coding: utf-8 -*-
# Team Chat - 主应用
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import uuid
import sqlite3

from config import *
from models import get_db, init_db, cleanup_expired_messages
from auth import hash_password, verify_password, login_required, admin_required, get_current_user

# 初始化 Flask 应用
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PERMANENT_SESSION_LIFETIME'] = PERMANENT_SESSION_LIFETIME

# 初始化 Socket.IO
# 生产环境应设置 SOCKETIO_CORS_ORIGINS 环境变量，如："https://yourdomain.com"
socketio_cors = os.environ.get('SOCKETIO_CORS_ORIGINS', '*')
if socketio_cors and socketio_cors != '*':
    socketio_cors = [origin.strip() for origin in socketio_cors.split(',')]
socketio = SocketIO(app, async_mode=SOCKETIO_ASYNC_MODE, cors_allowed_origins=socketio_cors)

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and verify_password(password, user['password_hash']):
            # 修复 Session 固定攻击：登录后重新生成 session
            session.regenerate()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nickname'] = user['nickname']
            session['is_admin'] = bool(user['is_admin'])
            session.permanent = True
            return redirect(url_for('chat'))
        
        return render_template('login.html', error='用户名或密码错误')
    
    return render_template('login.html')



@app.route('/logout')
def logout():
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
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 更新昵称
    cursor.execute("UPDATE users SET nickname = ? WHERE id = ?", (nickname, user['id']))
    
    # 修改密码
    if current_password and new_password:
        # 获取当前密码哈希
        cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user['id'],))
        row = cursor.fetchone()
        stored_hash = row['password_hash']
        
        # 验证当前密码
        if not verify_password(current_password, stored_hash):
            conn.close()
            return jsonify({'error': '当前密码错误'}), 400
        
        # 更新新密码
        new_hash = hash_password(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user['id']))
    
    conn.commit()
    conn.close()
    
    # 更新 session 中的昵称
    session['nickname'] = nickname
    
    return jsonify({
        'success': True,
        'nickname': nickname if nickname != user['nickname'] else None
    })

@app.route('/chat')
@login_required
def chat():
    user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取用户加入的群组
    cursor.execute('''
        SELECT g.* FROM groups g
        JOIN group_members gm ON g.id = gm.group_id
        WHERE gm.user_id = ?
        ORDER BY g.created_at DESC
    ''', (user['id'],))
    groups = cursor.fetchall()
    
    # 获取在线用户（简单实现：所有用户）
    cursor.execute("SELECT id, username, nickname, status FROM users")
    users = cursor.fetchall()
    
    conn.close()
    
    return render_template('chat.html', user=user, groups=groups, users=users)

@app.route('/admin')
@login_required
def admin():
    if not session.get('is_admin'):
        return redirect(url_for('chat'))
    
    user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取所有群组
    cursor.execute("SELECT * FROM groups ORDER BY created_at DESC")
    groups = []
    for row in cursor.fetchall():
        group = dict(row)
        # 转换 datetime 为字符串
        if 'created_at' in group and group['created_at']:
            group['created_at'] = str(group['created_at'])
        groups.append(group)
    
    # 获取所有用户
    cursor.execute("SELECT id, username, nickname, status, is_admin, created_at FROM users ORDER BY created_at DESC")
    users = []
    for row in cursor.fetchall():
        user_row = dict(row)
        # 转换 datetime 为字符串
        if 'created_at' in user_row and user_row['created_at']:
            user_row['created_at'] = str(user_row['created_at'])
        users.append(user_row)
    
    conn.close()
    
    return render_template('admin.html', user=user, groups=groups, users=users)

# ==================== API 路由 ====================

@app.route('/api/messages/<int:group_id>', methods=['GET'])
@login_required
def get_messages(group_id):
    """获取群组消息"""
    user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    # 验证用户是否在群组中
    cursor.execute(
        "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
        (group_id, user['id'])
    )
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': '无权访问此群组'}), 403
    
    # 获取消息（最近 100 条）
    cursor.execute('''
        SELECT m.*, u.username, u.nickname, u.avatar,
               f.filename, f.original_name, f.file_size, f.mime_type
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        LEFT JOIN files f ON m.file_id = f.id
        WHERE m.group_id = ?
        ORDER BY m.created_at DESC
        LIMIT 100
    ''', (group_id,))
    
    messages = []
    for row in cursor.fetchall():
        messages.append({
            'id': row['id'],
            'group_id': row['group_id'],
            'sender_id': row['sender_id'],
            'username': row['username'],
            'nickname': row['nickname'],
            'avatar': row['avatar'],
            'content': row['content'],
            'file': {
                'id': row['file_id'],
                'filename': row['filename'],
                'original_name': row['original_name'],
                'file_size': row['file_size'],
                'mime_type': row['mime_type']
            } if row['file_id'] else None,
            'created_at': row['created_at']
        })
    
    conn.close()
    messages.reverse()  # 按时间正序
    return jsonify(messages)

@app.route('/api/files/<int:file_id>')
@login_required
def download_file(file_id):
    """下载文件"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    file = cursor.fetchone()
    conn.close()
    
    if not file:
        return jsonify({'error': '文件不存在'}), 404
    
    # 增加下载次数
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE files SET download_count = download_count + 1 WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()
    
    return send_from_directory(UPLOAD_FOLDER, file['filename'], as_attachment=True, download_name=file['original_name'])

@app.route('/api/private_messages/<int:user_id>', methods=['GET'])
@login_required
def get_private_messages(user_id):
    """获取私聊消息"""
    current_user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取与指定用户的私聊消息（最近 100 条）
    cursor.execute('''
        SELECT pm.*, 
               u.username as sender_username, u.nickname as sender_nickname, u.avatar as sender_avatar,
               f.filename, f.original_name, f.file_size, f.mime_type
        FROM private_messages pm
        JOIN users u ON pm.sender_id = u.id
        LEFT JOIN files f ON pm.file_id = f.id
        WHERE (pm.sender_id = ? AND pm.receiver_id = ?)
           OR (pm.sender_id = ? AND pm.receiver_id = ?)
        ORDER BY pm.created_at DESC
        LIMIT 100
    ''', (current_user['id'], user_id, user_id, current_user['id']))
    
    messages = []
    for row in cursor.fetchall():
        messages.append({
            'id': row['id'],
            'sender_id': row['sender_id'],
            'receiver_id': row['receiver_id'],
            'username': row['sender_username'],
            'nickname': row['sender_nickname'],
            'avatar': row['sender_avatar'],
            'content': row['content'],
            'file': {
                'id': row['file_id'],
                'filename': row['filename'],
                'original_name': row['original_name'],
                'file_size': row['file_size'],
                'mime_type': row['mime_type']
            } if row['file_id'] else None,
            'created_at': row['created_at']
        })
    
    # 标记为已读
    cursor.execute('''
        UPDATE private_messages SET is_read = 1
        WHERE receiver_id = ? AND sender_id = ? AND is_read = 0
    ''', (current_user['id'], user_id))
    conn.commit()
    conn.close()
    
    messages.reverse()  # 按时间正序
    return jsonify(messages)

@app.route('/api/unread/count', methods=['GET'])
@login_required
def get_unread_count():
    """获取未读消息数量"""
    user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    # 群组未读消息数
    cursor.execute('''
        SELECT gm.group_id, COUNT(m.id) as unread_count
        FROM group_members gm
        LEFT JOIN unread_group_messages ugm ON gm.group_id = ugm.group_id AND ugm.user_id = ?
        LEFT JOIN messages m ON m.group_id = gm.group_id AND m.created_at > COALESCE(ugm.last_read_at, '1970-01-01') AND m.sender_id != ?
        WHERE gm.user_id = ?
        GROUP BY gm.group_id
    ''', (user['id'], user['id'], user['id']))
    
    group_unread = {}
    for row in cursor.fetchall():
        if row['unread_count'] > 0:
            group_unread[row['group_id']] = row['unread_count']
    
    # 私聊未读消息数
    cursor.execute('''
        SELECT sender_id, COUNT(*) as unread_count
        FROM private_messages
        WHERE receiver_id = ? AND is_read = 0
        GROUP BY sender_id
    ''', (user['id'],))
    
    private_unread = {}
    for row in cursor.fetchall():
        if row['unread_count'] > 0:
            private_unread[row['sender_id']] = row['unread_count']
    
    conn.close()
    
    return jsonify({
        'groups': group_unread,
        'private': private_unread
    })

@app.route('/api/mark_read/group/<int:group_id>', methods=['POST'])
@login_required
def mark_group_read(group_id):
    """标记群组消息为已读"""
    user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取群组最新消息 ID
    cursor.execute('SELECT MAX(id) as latest_id FROM messages WHERE group_id = ?', (group_id,))
    latest = cursor.fetchone()
    latest_id = latest['latest_id'] if latest and latest['latest_id'] else 0
    
    # 更新或插入未读记录
    cursor.execute('''
        INSERT OR REPLACE INTO unread_group_messages (user_id, group_id, last_read_message_id, last_read_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ''', (user['id'], group_id, latest_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/mark_read/private/<int:user_id>', methods=['POST'])
@login_required
def mark_private_read(user_id):
    """标记私聊消息为已读"""
    current_user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取与指定用户的最新消息 ID
    cursor.execute('''
        SELECT MAX(id) as latest_id FROM private_messages
        WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
    ''', (current_user['id'], user_id, user_id, current_user['id']))
    
    latest = cursor.fetchone()
    latest_id = latest['latest_id'] if latest and latest['latest_id'] else 0
    
    # 更新或插入未读记录
    cursor.execute('''
        INSERT OR REPLACE INTO unread_private_messages (user_id, sender_id, last_read_message_id, last_read_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ''', (current_user['id'], user_id, latest_id))
    
    # 标记私聊消息为已读
    cursor.execute('''
        UPDATE private_messages SET is_read = 1
        WHERE receiver_id = ? AND sender_id = ? AND is_read = 0
    ''', (current_user['id'], user_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/clear_unread', methods=['POST'])
@login_required
def clear_all_unread():
    """清空所有未读记录（可选功能）"""
    user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取当前最新消息 ID
    cursor.execute('SELECT MAX(id) as latest FROM messages')
    latest_group = cursor.fetchone()['latest'] or 0
    
    cursor.execute('SELECT MAX(id) as latest FROM private_messages')
    latest_private = cursor.fetchone()['latest'] or 0
    
    # 更新所有群组未读记录
    cursor.execute('''
        INSERT OR REPLACE INTO unread_group_messages (user_id, group_id, last_read_message_id, last_read_at)
        SELECT ?, group_id, ?, CURRENT_TIMESTAMP FROM group_members WHERE user_id = ?
    ''', (user['id'], latest_group, user['id']))
    
    # 更新所有私聊未读记录
    cursor.execute('''
        INSERT OR REPLACE INTO unread_private_messages (user_id, sender_id, last_read_message_id, last_read_at)
        SELECT DISTINCT ?, sender_id, ?, CURRENT_TIMESTAMP 
        FROM private_messages 
        WHERE receiver_id = ?
    ''', (user['id'], latest_private, user['id']))
    
    # 标记所有消息为已读
    cursor.execute('''
        UPDATE private_messages SET is_read = 1 WHERE receiver_id = ?
    ''', (user['id'],))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ==================== Socket.IO 事件 ====================

@socketio.on('join_group')
def on_join_group(data):
    """加入群组房间"""
    group_id = data['group_id']
    join_room(f"group_{group_id}")
    print(f"用户 {session.get('username')} 加入群组 {group_id}")

@socketio.on('leave_group')
def on_leave_group(data):
    """离开群组房间"""
    group_id = data['group_id']
    leave_room(f"group_{group_id}")
    print(f"用户 {session.get('username')} 离开群组 {group_id}")

@socketio.on('send_message')
def on_send_message(data):
    """发送消息"""
    if 'user_id' not in session:
        return {'error': '请先登录'}
    
    group_id = data.get('group_id')
    content = data.get('content', '').strip()
    file_id = data.get('file_id')
    
    if not content and not file_id:
        return {'error': '消息不能为空'}
    
    user = get_current_user()
    expires_at = datetime.now() + timedelta(days=MESSAGE_RETENTION_DAYS)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 插入消息
    cursor.execute('''
        INSERT INTO messages (group_id, sender_id, content, file_id, expires_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (group_id, user['id'], content if content else None, file_id, expires_at))
    
    message_id = cursor.lastrowid
    conn.commit()
    
    # 获取消息详情
    cursor.execute('''
        SELECT m.*, u.username, u.nickname, u.avatar,
               f.filename, f.original_name, f.file_size, f.mime_type
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        LEFT JOIN files f ON m.file_id = f.id
        WHERE m.id = ?
    ''', (message_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    message = {
        'id': row['id'],
        'group_id': row['group_id'],
        'sender_id': row['sender_id'],
        'username': row['username'],
        'nickname': row['nickname'],
        'avatar': row['avatar'],
        'content': row['content'],
        'file': {
            'id': row['file_id'],
            'filename': row['filename'],
            'original_name': row['original_name'],
            'file_size': row['file_size'],
            'mime_type': row['mime_type']
        } if row['file_id'] else None,
        'created_at': row['created_at']
    }
    
    # 广播给群组
    emit('new_message', message, room=f"group_{group_id}")
    return {'success': True, 'message_id': message_id}

@socketio.on('join_private')
def on_join_private(data):
    """加入私聊房间"""
    user_id = data['user_id']
    current_user = get_current_user()
    # 私聊房间名格式：private_user1_user2（用户 ID 小的在前，确保唯一）
    room_users = sorted([current_user['id'], user_id])
    room_name = f"private_{room_users[0]}_{room_users[1]}"
    join_room(room_name)
    print(f"用户 {current_user['username']} 加入私聊房间 {room_name}")

@socketio.on('leave_private')
def on_leave_private(data):
    """离开私聊房间"""
    user_id = data['user_id']
    current_user = get_current_user()
    room_users = sorted([current_user['id'], user_id])
    room_name = f"private_{room_users[0]}_{room_users[1]}"
    leave_room(room_name)
    print(f"用户 {current_user['username']} 离开私聊房间 {room_name}")

@socketio.on('send_private_message')
def on_send_private_message(data):
    """发送私聊消息"""
    if 'user_id' not in session:
        return {'error': '请先登录'}
    
    receiver_id = data.get('receiver_id')
    content = data.get('content', '').strip()
    file_id = data.get('file_id')
    
    if not content and not file_id:
        return {'error': '消息不能为空'}
    
    user = get_current_user()
    expires_at = datetime.now() + timedelta(days=MESSAGE_RETENTION_DAYS)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 插入私聊消息
    cursor.execute('''
        INSERT INTO private_messages (sender_id, receiver_id, content, file_id, expires_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user['id'], receiver_id, content if content else None, file_id, expires_at))
    
    message_id = cursor.lastrowid
    conn.commit()
    
    # 获取消息详情
    cursor.execute('''
        SELECT pm.*, 
               u.username, u.nickname, u.avatar,
               f.filename, f.original_name, f.file_size, f.mime_type
        FROM private_messages pm
        JOIN users u ON pm.sender_id = u.id
        LEFT JOIN files f ON pm.file_id = f.id
        WHERE pm.id = ?
    ''', (message_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    message = {
        'id': row['id'],
        'sender_id': row['sender_id'],
        'receiver_id': row['receiver_id'],
        'username': row['username'],
        'nickname': row['nickname'],
        'avatar': row['avatar'],
        'content': row['content'],
        'file': {
            'id': row['file_id'],
            'filename': row['filename'],
            'original_name': row['original_name'],
            'file_size': row['file_size'],
            'mime_type': row['mime_type']
        } if row['file_id'] else None,
        'created_at': row['created_at']
    }
    
    # 发送到私聊房间（双方都能收到）
    room_users = sorted([user['id'], receiver_id])
    room_name = f"private_{room_users[0]}_{room_users[1]}"
    emit('new_private_message', message, room=room_name)
    
    return {'success': True, 'message_id': message_id}

@socketio.on('upload_file')
def on_upload_file(data):
    """上传文件"""
    if 'user_id' not in session:
        return {'error': '请先登录'}
    
    # 这里处理 base64 文件数据
    # 实际实现需要前端配合
    return {'error': '文件上传请使用 HTTP POST'}

# ==================== 管理员 API ====================

@app.route('/api/admin/create_user', methods=['POST'])
@admin_required
def create_user():
    """创建用户"""
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
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash, nickname, is_admin) VALUES (?, ?, ?, ?)",
            (username, password_hash, nickname, 1 if is_admin else 0)
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': '用户名已存在'}), 400

@app.route('/api/group_members/<int:group_id>', methods=['GET'])
@login_required
def get_group_members_public(group_id):
    """获取群组成员列表（普通用户可访问）"""
    user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    # 验证用户是否在群组中
    cursor.execute(
        "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
        (group_id, user['id'])
    )
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': '无权访问此群组'}), 403
    
    cursor.execute('''
        SELECT u.id, u.username, u.nickname, gm.role, gm.joined_at, u.status
        FROM group_members gm
        JOIN users u ON gm.user_id = u.id
        WHERE gm.group_id = ?
        ORDER BY gm.joined_at ASC
    ''', (group_id,))
    
    members = []
    for row in cursor.fetchall():
        member = dict(row)
        # 确保 nickname 不为空
        if not member['nickname']:
            member['nickname'] = member['username']
        members.append(member)
    
    conn.close()
    
    return jsonify(members)

@app.route('/api/admin/group_members/<int:group_id>', methods=['GET'])
@admin_required
def get_group_members_admin(group_id):
    """获取群组成员列表（管理员专用）"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.id, u.username, u.nickname, gm.role, gm.joined_at, u.status
        FROM group_members gm
        JOIN users u ON gm.user_id = u.id
        WHERE gm.group_id = ?
        ORDER BY gm.joined_at ASC
    ''', (group_id,))
    
    members = []
    for row in cursor.fetchall():
        member = dict(row)
        if not member['nickname']:
            member['nickname'] = member['username']
        members.append(member)
    
    conn.close()
    
    return jsonify(members)

@app.route('/api/admin/user_groups/<int:user_id>', methods=['GET'])
@admin_required
def get_user_groups(user_id):
    """获取用户已加入的群组"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT g.id, g.name, g.description 
        FROM groups g
        JOIN group_members gm ON g.id = gm.group_id
        WHERE gm.user_id = ?
        ORDER BY g.created_at DESC
    ''', (user_id,))
    
    groups = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(groups)

@app.route('/api/admin/create_group', methods=['POST'])
@admin_required
def create_group():
    """创建群组"""
    name = request.json.get('name', '').strip()
    description = request.json.get('description', '').strip()
    
    if not name:
        return jsonify({'error': '群组名称不能为空'}), 400
    
    user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO groups (name, description, created_by) VALUES (?, ?, ?)",
        (name, description, user['id'])
    )
    group_id = cursor.lastrowid
    
    # 创建者不自动加入群组
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'group_id': group_id})

@app.route('/api/admin/add_member', methods=['POST'])
@admin_required
def add_member():
    """添加群组成员"""
    group_id = request.json.get('group_id')
    user_id = request.json.get('user_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, user_id)
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': '用户已在群组中'}), 400

@app.route('/api/admin/remove_member', methods=['POST'])
@admin_required
def remove_member():
    """移除群组成员"""
    group_id = request.json.get('group_id')
    user_id = request.json.get('user_id')
    
    if not group_id or not user_id:
        return jsonify({'error': '参数错误'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM group_members WHERE group_id = ? AND user_id = ?",
        (group_id, user_id)
    )
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/admin/delete_group', methods=['POST'])
@admin_required
def delete_group():
    """删除群组"""
    group_id = request.json.get('group_id')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ==================== 文件上传 ====================

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    """上传文件"""
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400
    
    # 验证文件扩展名
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': '不支持的文件类型'}), 400
    
    # 生成唯一文件名
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    
    # 保存文件
    file.save(file_path)
    file_size = os.path.getsize(file_path)
    
    # 检测 MIME 类型
    mime_type = file.content_type or 'application/octet-stream'
    
    user = get_current_user()
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO files (filename, original_name, file_path, file_size, mime_type, uploaded_by)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (unique_filename, file.filename, file_path, file_size, mime_type, user['id']))
    
    file_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'file_id': file_id,
        'filename': file.filename,
        'file_size': file_size,
        'mime_type': mime_type
    })

# ==================== 定时清理 ====================

def start_cleanup_scheduler():
    """启动定时清理任务"""
    import threading
    import time
    
    def cleanup_loop():
        while True:
            now = datetime.now()
            if now.hour == 2 and now.minute == 0:
                cleanup_expired_messages()
                time.sleep(60)  # 避免同一分钟内重复执行
            else:
                time.sleep(30)
    
    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    print("🕐 定时清理任务已启动（每天凌晨 2 点）")

# ==================== 应用启动 ====================

if __name__ == '__main__':
    # 初始化数据库
    init_db()
    
    # 创建默认管理员
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE username = ?", (ADMIN_USERNAME,))
    if not cursor.fetchone():
        password_hash = hash_password(ADMIN_PASSWORD)
        cursor.execute(
            "INSERT INTO users (username, password_hash, nickname, is_admin) VALUES (?, ?, ?, ?)",
            (ADMIN_USERNAME, password_hash, '管理员', 1)
        )
        conn.commit()
        print(f"✅ 默认管理员已创建：{ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    conn.close()
    
    # 启动清理任务
    start_cleanup_scheduler()
    
    # 启动应用
    print("\n🚀 Team Chat 启动中...")
    print("📍 访问地址：http://127.0.0.1:5001")
    print("💡 按 Ctrl+C 停止服务\n")
    
    socketio.run(app, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True)
