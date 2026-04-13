# Team Chat - 用户认证模块
import hashlib
import os
from functools import wraps
from flask import session, redirect, url_for, request, jsonify

def hash_password(password, salt=None):
    """密码哈希（6 万次迭代，符合 OWASP 2023）"""
    if salt is None:
        salt = os.urandom(16).hex()
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        60000  # 6 万次迭代
    ).hex()
    return f"{salt}${password_hash}"

def verify_password(password, stored_hash):
    """验证密码"""
    try:
        salt, hash_value = stored_hash.split('$')
        new_hash = hash_password(password, salt)
        return new_hash == stored_hash
    except (ValueError, AttributeError):
        return False

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.headers.get('Accept', '').startswith('application/json'):
                return jsonify({'error': '请先登录'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """管理员验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.headers.get('Accept', '').startswith('application/json'):
                return jsonify({'error': '请先登录'}), 401
            return redirect(url_for('login'))
        if not session.get('is_admin'):
            if request.is_json or request.headers.get('Accept', '').startswith('application/json'):
                return jsonify({'error': '需要管理员权限'}), 403
            return redirect(url_for('chat'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """获取当前用户信息"""
    if 'user_id' not in session:
        return None
    return {
        'id': session['user_id'],
        'username': session['username'],
        'nickname': session['nickname'],
        'is_admin': session.get('is_admin', False)
    }
