# Team Chat - 数据库模型
import sqlite3
import os
import logging
from datetime import datetime, timedelta
from config import DATABASE_PATH, MESSAGE_RETENTION_DAYS, UPLOAD_FOLDER

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """数据库连接上下文管理器，防止连接泄漏"""

    def __init__(self):
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(DATABASE_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")  # 开启 WAL 模式，提升并发性能
        self.conn.execute("PRAGMA foreign_keys=ON")    # 开启外键约束
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()


def get_db():
    """获取数据库连接（兼容旧代码，推荐使用 DatabaseConnection）"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库"""
    conn = get_db()
    cursor = conn.cursor()

    # 用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nickname TEXT NOT NULL,
            avatar TEXT DEFAULT '',
            status TEXT DEFAULT 'offline',
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 分组表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    ''')

    # 群组成员表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(group_id, user_id)
        )
    ''')

    # 消息表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT,
            file_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL
        )
    ''')

    # 文件表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            mime_type TEXT NOT NULL,
            uploaded_by INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            download_count INTEGER DEFAULT 0,
            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL,
            FOREIGN KEY (uploaded_by) REFERENCES users(id)
        )
    ''')

    # 私聊消息表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS private_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            content TEXT,
            file_id INTEGER,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id),
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL
        )
    ''')

    # 未读消息记录表（群组）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS unread_group_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            last_read_message_id INTEGER DEFAULT 0,
            last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            UNIQUE(user_id, group_id)
        )
    ''')

    # 未读消息记录表（私聊）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS unread_private_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            last_read_message_id INTEGER DEFAULT 0,
            last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, sender_id)
        )
    ''')

    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_group ON messages(group_id, created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_expires ON messages(expires_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_private_messages ON private_messages(sender_id, receiver_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_private_messages_read ON private_messages(receiver_id, is_read)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_group_members ON group_members(group_id, user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_uploaded ON files(uploaded_at)')

    conn.commit()
    conn.close()
    logger.info("数据库初始化完成（WAL 模式已启用）")


def cleanup_expired_messages():
    """清理过期消息、关联文件和无效未读记录"""
    deleted_files = 0

    with DatabaseConnection() as conn:
        cursor = conn.cursor()

        cutoff = datetime.now() - timedelta(days=MESSAGE_RETENTION_DAYS)

        # 1. 先找出要删除的消息关联的文件，删除磁盘文件
        cursor.execute('''
            SELECT f.id, f.file_path FROM files f
            JOIN messages m ON f.message_id = m.id
            WHERE m.expires_at < ?
        ''', (cutoff,))
        for row in cursor.fetchall():
            if row['file_path'] and os.path.exists(row['file_path']):
                try:
                    os.remove(row['file_path'])
                    deleted_files += 1
                except OSError as e:
                    logger.warning(f"删除文件失败 {row['file_path']}: {e}")

        # 私聊关联文件
        cursor.execute('''
            SELECT f.id, f.file_path FROM files f
            JOIN private_messages pm ON f.message_id = pm.id
            WHERE pm.expires_at < ?
        ''', (cutoff,))
        for row in cursor.fetchall():
            if row['file_path'] and os.path.exists(row['file_path']):
                try:
                    os.remove(row['file_path'])
                    deleted_files += 1
                except OSError as e:
                    logger.warning(f"删除文件失败 {row['file_path']}: {e}")

        # 2. 删除过期群消息
        cursor.execute("DELETE FROM messages WHERE expires_at < ?", (cutoff,))
        group_deleted = cursor.rowcount

        # 3. 删除过期私聊消息
        cursor.execute("DELETE FROM private_messages WHERE expires_at < ?", (cutoff,))
        private_deleted = cursor.rowcount

        # 4. 清理无引用的孤立文件记录
        cursor.execute('''
            DELETE FROM files WHERE message_id IS NOT NULL
            AND message_id NOT IN (SELECT file_id FROM messages WHERE file_id IS NOT NULL)
            AND message_id NOT IN (SELECT file_id FROM private_messages WHERE file_id IS NOT NULL)
        ''')
        orphan_files = cursor.rowcount

        # 5. 清理无效未读记录（用户已退出的群组）
        cursor.execute('''
            DELETE FROM unread_group_messages ugm
            WHERE NOT EXISTS (
                SELECT 1 FROM group_members gm
                WHERE gm.user_id = ugm.user_id AND gm.group_id = ugm.group_id
            )
        ''')
        orphan_group = cursor.rowcount

        # 6. 清理无效未读记录（用户已删除）
        cursor.execute('''
            DELETE FROM unread_private_messages upm
            WHERE NOT EXISTS (
                SELECT 1 FROM users u WHERE u.id = upm.user_id
            )
        ''')
        orphan_private = cursor.rowcount

    total = group_deleted + private_deleted + orphan_group + orphan_private
    if total > 0 or deleted_files > 0:
        logger.info(
            f"清理完成: 群消息 {group_deleted}, 私聊 {private_deleted}, "
            f"群未读 {orphan_group}, 私聊未读 {orphan_private}, "
            f"磁盘文件 {deleted_files}, 孤立文件记录 {orphan_files}"
        )

    return total


# 初始化数据库
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    init_db()
