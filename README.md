# Team Chat - 团队聊天工具开发文档

**版本**: v0.1.0  
**最后更新**: 2026-03-17  
**GitHub**: https://github.com/zhouyaya100/team-chat

---

## 📋 项目概述

Team Chat 是一个轻量级的团队聊天工具，支持群组聊天、私聊、文件传输等功能。采用 Flask + Socket.IO 实现实时通信，SQLite 作为数据库。

### 核心特性

- ✅ **用户系统** - 管理员添加用户，无公开注册
- ✅ **群组聊天** - WebSocket 实时消息
- ✅ **私聊功能** - 一对一加密聊天
- ✅ **文件传输** - 支持图片/视频，最大 100MB
- ✅ **消息清理** - 10 天自动清理
- ✅ **浏览器通知** - 最小化也能收到通知
- ✅ **未读角标** - 实时显示未读消息数
- ✅ **成员管理** - 管理员可创建群组、添加成员
- ✅ **用户颜色区分** - 不同用户的消息气泡颜色不同

---

## 🛠️ 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 后端 | Flask | 3.0 |
| 实时通信 | Flask-SocketIO | 5.3.6 |
| 前端 | Bootstrap 5 | 5.3 |
| 数据库 | SQLite | 内置 |
| 密码哈希 | Werkzeug | 内置 |

---

## 📁 项目结构

```
team-chat/
├── app.py              # Flask 主应用 + Socket.IO + API 路由
├── auth.py             # 用户认证（登录验证、装饰器）
├── config.py           # 配置（上传限制、消息保留天数等）
├── models.py           # 数据库模型 + 初始化 + 清理任务
├── requirements.txt    # Python 依赖
├── start.bat           # Windows 启动脚本
├── start.sh            # Linux/Mac 启动脚本
└── templates/
    ├── base.html       # 基础模板（含个人资料模态框）
    ├── login.html      # 登录页
    ├── chat.html       # 聊天页（含成员面板、通知功能）
    └── admin.html      # 管理后台（实时刷新）
```

---

## 🗄️ 数据库设计

### 表结构

#### users - 用户表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| username | TEXT | 用户名（唯一） |
| password | TEXT | 密码哈希 |
| nickname | TEXT | 昵称 |
| avatar | TEXT | 头像 URL |
| status | TEXT | 在线状态 (online/offline) |
| is_admin | BOOLEAN | 是否管理员 |
| created_at | DATETIME | 创建时间 |

#### groups - 群组表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| name | TEXT | 群组名称 |
| description | TEXT | 群组描述 |
| created_at | DATETIME | 创建时间 |

#### group_members - 群组成员表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| group_id | INTEGER | 群组 ID |
| user_id | INTEGER | 用户 ID |
| role | TEXT | 角色 (admin/member) |
| joined_at | DATETIME | 加入时间 |

#### messages - 群消息表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| group_id | INTEGER | 群组 ID |
| sender_id | INTEGER | 发送者 ID |
| content | TEXT | 消息内容 |
| file_id | INTEGER | 文件 ID（可选） |
| created_at | DATETIME | 创建时间（UTC） |
| expires_at | DATETIME | 过期时间 |

#### private_messages - 私聊消息表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| sender_id | INTEGER | 发送者 ID |
| receiver_id | INTEGER | 接收者 ID |
| content | TEXT | 消息内容 |
| file_id | INTEGER | 文件 ID（可选） |
| created_at | DATETIME | 创建时间（UTC） |
| expires_at | DATETIME | 过期时间 |

#### files - 文件表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| filename | TEXT | 存储文件名 |
| original_name | TEXT | 原始文件名 |
| file_size | INTEGER | 文件大小（字节） |
| mime_type | TEXT | MIME 类型 |
| upload_count | INTEGER | 上传次数 |
| download_count | INTEGER | 下载次数 |
| uploaded_at | DATETIME | 上传时间 |

---

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务

**Windows:**
```bash
start.bat
```

**Linux/Mac:**
```bash
./start.sh
```

**手动启动:**
```bash
python app.py
```

### 访问地址

- 本地：http://127.0.0.1:5001
- 局域网：http://<服务器 IP>:5001

### 默认管理员

- 用户名：`admin`
- 密码：`Admin@123`

**⚠️ 首次登录后请立即修改密码！**

---

## 📡 API 文档

### 认证相关

#### POST /api/login
登录
```json
{
  "username": "admin",
  "password": "Admin@123"
}
```

#### POST /api/logout
登出

### 消息相关

#### GET /api/messages/<group_id>
获取群组消息（最近 100 条）

#### GET /api/private_messages/<user_id>
获取私聊消息（最近 100 条）

#### POST /api/mark_read/group/<group_id>
标记群组消息为已读

#### POST /api/mark_read/private/<user_id>
标记私聊消息为已读

#### GET /api/unread/count
获取未读消息数量

### 文件相关

#### POST /api/upload
上传文件

#### GET /api/files/<file_id>
下载文件

### 管理员 API

#### GET /api/admin/groups
获取所有群组

#### POST /api/admin/groups
创建群组

#### DELETE /api/admin/groups/<id>
删除群组

#### GET /api/admin/group_members/<group_id>
获取群组成员（管理员）

#### POST /api/admin/group_members
添加群组成员

#### DELETE /api/admin/group_members/<id>
移除群组成员

#### GET /api/admin/users
获取所有用户

#### POST /api/admin/users
创建用户

#### DELETE /api/admin/users/<id>
删除用户

---

## 🔌 Socket.IO 事件

### 客户端 → 服务器

| 事件 | 参数 | 说明 |
|------|------|------|
| `join_group` | `{ group_id: number }` | 加入群组房间 |
| `leave_group` | `{ group_id: number }` | 离开群组房间 |
| `join_private` | `{ user_id: number }` | 加入私聊房间 |
| `leave_private` | `{ user_id: number }` | 离开私聊房间 |
| `send_message` | `{ group_id, content, file_id }` | 发送群消息 |
| `send_private_message` | `{ receiver_id, content, file_id }` | 发送私聊消息 |

### 服务器 → 客户端

| 事件 | 数据 | 说明 |
|------|------|------|
| `new_message` | Message 对象 | 收到群消息 |
| `new_private_message` | Message 对象 | 收到私聊消息 |
| `user_joined` | `{ user_id, username }` | 用户加入 |
| `user_left` | `{ user_id, username }` | 用户离开 |

---

## 🎨 功能实现细节

### 1. 消息自动清理

每天凌晨 2 点自动清理 10 天前的消息：

```python
def cleanup_expired_messages():
    cutoff = datetime.now() - timedelta(days=MESSAGE_RETENTION_DAYS)
    # 清理群消息
    cursor.execute("DELETE FROM messages WHERE expires_at < ?", (cutoff,))
    # 清理私聊消息
    cursor.execute("DELETE FROM private_messages WHERE expires_at < ?", (cutoff,))
    conn.commit()
```

### 2. 私聊房间命名

确保唯一性（用户 ID 小的在前）：

```python
room_users = sorted([user1_id, user2_id])
room_name = f"private_{room_users[0]}_{room_users[1]}"
```

### 3. 浏览器通知

```javascript
Notification.requestPermission()
new Notification(title, {
    body: body,
    icon: '/static/icon.png',
    badge: '/static/badge.png'
})
```

### 4. 提示音（Web Audio API）

```javascript
const oscillator = audioContext.createOscillator()
oscillator.frequency.value = 800  // 800Hz
oscillator.type = 'sine'
gainNode.gain.setValueAtTime(0.3, audioContext.currentTime)
gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3)
oscillator.start()
oscillator.stop(audioContext.currentTime + 0.3)
```

### 5. 用户消息颜色区分

每个用户根据 ID 固定分配一个颜色：

```javascript
function getUserColorIndex(userId) {
    if (!userColorMap[userId]) {
        userColorMap[userId] = (userId % 8) + 1;
    }
    return userColorMap[userId];
}
```

### 6. 时间显示（UTC → 北京时间）

数据库存 UTC 时间，前端转换为北京时间：

```javascript
// 数据库："2026-03-17 08:42:00" (UTC)
const date = new Date(createdAt.replace(' ', 'T') + 'Z');
const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
// 显示："16:42" (北京)
```

---

## 🔒 安全特性

- ✅ 密码哈希存储（Werkzeug，6 万次迭代）
- ✅ 登录验证装饰器
- ✅ 文件上传限制（100MB）
- ✅ 文件类型白名单（图片/视频）
- ✅ 消息过期自动清理
- ✅ 管理员权限分离

---

## 📝 配置说明

### config.py

```python
# 上传限制
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
UPLOAD_FOLDER = 'uploads'

# 消息保留天数
MESSAGE_RETENTION_DAYS = 10

# Session 配置
SECRET_KEY = 'your-secret-key-here'
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

# Socket.IO 配置
SOCKETIO_ASYNC_MODE = 'threading'
```

---

## 🐛 已知问题

1. **文件清理** - 消息清理时不会删除对应的文件（待优化）
2. **集群支持** - 当前版本不支持多服务器部署（Socket.IO 房间）
3. **消息搜索** - 暂不支持消息搜索功能

---

## 📅 更新日志

### v0.1.0 (2026-03-17)

**新功能**
- ✅ 群组聊天
- ✅ 私聊功能
- ✅ 文件上传（图片/视频）
- ✅ 浏览器通知
- ✅ 未读角标
- ✅ 用户消息颜色区分
- ✅ 管理员后台
- ✅ 消息 10 天自动清理

**优化**
- ✅ 时间显示转换为北京时间
- ✅ WebSocket 连接优化
- ✅ 页面加载性能优化

---

## 📄 许可证

MIT License

---

## 👥 开发团队

- **开发者**: NotJustSRE
- **GitHub**: https://github.com/zhouyaya100

---

## 🙏 致谢

感谢以下开源项目：

- [Flask](https://flask.palletsprojects.com/)
- [Flask-SocketIO](https://flask-socketio.readthedocs.io/)
- [Bootstrap 5](https://getbootstrap.com/)
