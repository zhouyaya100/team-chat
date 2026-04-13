# Team Chat - 团队聊天工具

**版本**: v0.2.0  
**最后更新**: 2026-04-13  
**GitHub**: https://github.com/zhouyaya100/team-chat

---

## 📋 项目概述

Team Chat 是一个轻量级的团队聊天工具，支持群组聊天、私聊、文件传输等功能。采用 Flask + Socket.IO 实现实时通信，SQLite 作为数据库。

### 核心特性

- ✅ **用户系统** — 管理员添加用户，无公开注册
- ✅ **群组聊天** — WebSocket 实时消息
- ✅ **私聊功能** — 一对一聊天
- ✅ **文件传输** — 支持图片/视频，最大 100MB
- ✅ **消息清理** — 10 天自动清理（含磁盘文件）
- ✅ **浏览器通知** — 最小化也能收到通知 + 提示音
- ✅ **未读角标** — 实时显示未读消息数
- ✅ **在线状态** — WebSocket 驱动的实时在线/离线状态
- ✅ **成员管理** — 管理员可创建群组、添加/移除成员
- ✅ **消息分页** — 支持加载更多历史消息
- ✅ **实时搜索** — 侧边栏搜索群组和联系人
- ✅ **用户颜色区分** — 不同用户的消息气泡颜色不同

---

## 🛠️ 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 后端 | Flask | 3.0+ |
| 实时通信 | Flask-SocketIO | 5.3.6+ |
| 前端 | Bootstrap 5 | 5.3 |
| 数据库 | SQLite (WAL 模式) | 内置 |
| 密码哈希 | PBKDF2-SHA256 (60k 迭代) | 内置 |
| 定时任务 | APScheduler | 3.10+ |
| 环境变量 | python-dotenv | 1.0+ |

---

## 📁 项目结构

```
team-chat/
├── app.py              # Flask 主应用 + Socket.IO + API 路由
├── auth.py             # 用户认证（登录验证、装饰器）
├── config.py           # 配置（上传限制、消息保留天数等）
├── models.py           # 数据库模型 + 上下文管理器 + 清理任务
├── requirements.txt    # Python 依赖
├── start.bat           # Windows 启动脚本
├── start.sh            # Linux/Mac 启动脚本
├── .env.example        # 环境变量模板
├── static/             # 本地静态资源（CSS/JS/字体）
│   ├── css/
│   │   ├── bootstrap.min.css
│   │   └── all.min.css
│   ├── js/
│   │   ├── bootstrap.bundle.min.js
│   │   └── socket.io.min.js
│   └── webfonts/
└── templates/
    ├── base.html       # 基础模板（含个人资料模态框）
    ├── login.html      # 登录页
    ├── chat.html       # 聊天页（含搜索、通知、成员面板）
    └── admin.html      # 管理后台（含统计卡片、表格管理）
```

---

## 🗄️ 数据库设计

### 表结构

#### users - 用户表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| username | TEXT | 用户名（唯一） |
| password_hash | TEXT | 密码哈希 |
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
| created_by | INTEGER | 创建者 ID |
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
| is_read | BOOLEAN | 是否已读 |
| created_at | DATETIME | 创建时间（UTC） |
| expires_at | DATETIME | 过期时间 |

#### files - 文件表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| message_id | INTEGER | 关联消息 ID |
| filename | TEXT | 存储文件名 |
| original_name | TEXT | 原始文件名 |
| file_path | TEXT | 文件路径 |
| file_size | INTEGER | 文件大小（字节） |
| mime_type | TEXT | MIME 类型 |
| uploaded_by | INTEGER | 上传者 ID |
| uploaded_at | DATETIME | 上传时间 |
| download_count | INTEGER | 下载次数 |

---

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量（可选）

```bash
# 复制模板
cp .env.example .env

# 编辑 .env 文件，设置 SECRET_KEY 等敏感配置
```

### 启动服务

**Windows:**
```bash
start.bat
```

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

**手动启动:**
```bash
python app.py
```

### 访问地址

- 本地：http://127.0.0.1:5001
- 局域网：http://\<服务器 IP\>:5001

### 默认管理员

- 用户名：`admin`
- 密码：`Admin@123`

**⚠️ 首次登录后请立即修改密码！**

---

## 🔒 安全特性

- ✅ 密码哈希存储（PBKDF2-SHA256，6 万次迭代，OWASP 2023 标准）
- ✅ 登录验证装饰器（区分 API/浏览器请求）
- ✅ Session 固定攻击防护（登录后重建 session）
- ✅ XSS 防护（消息内容 HTML 转义）
- ✅ SQL 注入防护（参数化查询）
- ✅ 文件上传服务端 MIME 校验（不信任客户端 content-type）
- ✅ 文件路径遍历防护（文件名安全检查 + 路径范围校验）
- ✅ 文件上传限制（100MB）
- ✅ 文件类型白名单（图片/视频）
- ✅ 群消息发送权限校验（验证用户是否在群组）
- ✅ 私聊接收者校验（验证用户存在 + 禁止自聊）
- ✅ CORS 配置支持（可限制域名）
- ✅ 消息过期自动清理（含磁盘文件删除）
- ✅ 管理员权限分离
- ✅ 环境变量支持 + .env 文件（python-dotenv）
- ✅ SQLite WAL 模式（提升并发性能）
- ✅ 数据库外键约束（PRAGMA foreign_keys=ON）
- ✅ 数据库连接上下文管理器（自动 commit/rollback，防泄漏）

---

## 🔒 安全配置

### 环境变量（生产环境必备）

**.env 文件:**
```
SECRET_KEY=your-64-character-random-secret-key-here
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourStrongPassword123!
SOCKETIO_CORS_ORIGINS=https://yourdomain.com
```

**生成 SECRET_KEY:**
```bash
python -c "import os; print(os.urandom(32).hex())"
```

### 安全建议

1. **SECRET_KEY**: 使用 64 字符随机密钥
2. **ADMIN_PASSWORD**: 至少 12 位，包含大小写字母、数字、特殊字符
3. **SOCKETIO_CORS_ORIGINS**: 设置为你的域名，不要用 `*`
4. **HTTPS**: 生产环境务必使用 HTTPS
5. **防火墙**: 仅开放必要端口（如 5001）
6. **WSGI 服务器**: 生产环境使用 Gunicorn/Waitress 替代 Flask 开发服务器

---

## 📡 API 文档

### 认证相关

#### POST /api/login
登录
```json
{ "username": "admin", "password": "Admin@123" }
```

#### POST /api/logout
登出

#### POST /api/update_profile
更新个人资料和密码
```json
{
  "nickname": "新昵称",
  "current_password": "旧密码",
  "new_password": "新密码"
}
```

### 消息相关

#### GET /api/messages/\<group_id\>
获取群组消息（支持分页）

参数：`before_id` - 加载此 ID 之前的消息

#### GET /api/private_messages/\<user_id\>
获取私聊消息（支持分页）

参数：`before_id` - 加载此 ID 之前的消息

#### POST /api/mark_read/group/\<group_id\>
标记群组消息为已读

#### POST /api/mark_read/private/\<user_id\>
标记私聊消息为已读

#### POST /api/clear_unread
清空所有未读记录

#### GET /api/unread/count
获取未读消息数量

### 文件相关

#### POST /api/upload
上传文件（multipart/form-data）

#### GET /api/files/\<file_id\>
下载文件

### 群组成员

#### GET /api/group_members/\<group_id\>
获取群组成员列表（需为群组成员）

### 管理员 API

#### POST /api/admin/create_user
创建用户

#### DELETE /api/admin/delete_user/\<user_id\>
删除用户

#### GET /api/admin/groups
获取所有群组

#### POST /api/admin/create_group
创建群组（创建者自动加入为 admin）

#### DELETE /api/admin/delete_group
删除群组

#### GET /api/admin/group_members/\<group_id\>
获取群组成员列表

#### POST /api/admin/add_member
添加群组成员

#### POST /api/admin/remove_member
移除群组成员

#### GET /api/admin/user_groups/\<user_id\>
获取用户已加入的群组

---

## 🔌 Socket.IO 事件

### 客户端 → 服务器

| 事件 | 参数 | 说明 |
|------|------|------|
| `join_group` | `{ group_id }` | 加入群组房间 |
| `leave_group` | `{ group_id }` | 离开群组房间 |
| `send_message` | `{ group_id, content, file_id }` | 发送群消息 |
| `join_private` | `{ user_id }` | 加入私聊房间 |
| `leave_private` | `{ user_id }` | 离开私聊房间 |
| `send_private_message` | `{ receiver_id, content, file_id }` | 发送私聊消息 |

### 服务器 → 客户端

| 事件 | 数据 | 说明 |
|------|------|------|
| `new_message` | Message 对象 | 收到群消息 |
| `new_private_message` | Message 对象 | 收到私聊消息 |
| `user_status_change` | `{ user_id, status }` | 用户在线状态变更 |

---

## 📝 配置说明

### config.py

```python
# 上传限制
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
UPLOAD_FOLDER = 'uploads'

# 消息保留天数
MESSAGE_RETENTION_DAYS = 10

# 消息分页
MESSAGES_PER_PAGE = 50

# Session 配置
SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24).hex())
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

# Socket.IO 配置
SOCKETIO_ASYNC_MODE = 'threading'
```

---

## 📅 更新日志

### v0.2.0 (2026-04-13)

**安全修复**
- 🔴 修复 `session.regenerate()` 不存在导致登录崩溃
- 🔴 文件下载合并为单事务，防连接泄漏
- 🔴 新增服务端 MIME 类型校验（不信任客户端）
- 🔴 新增文件路径遍历防护
- 🔴 消息清理时同步删除磁盘文件

**功能改进**
- 🟡 SQLite 启用 WAL 模式，提升并发性能
- 🟡 APScheduler 替代线程轮询定时任务
- 🟡 群消息发送增加权限校验
- 🟡 私聊增加接收者校验 + 禁止自聊
- 🟡 创建群组后创建者自动以 admin 身份加入
- 🟡 新增删除用户 API (`DELETE /api/admin/delete_user/<id>`)
- 🟡 管理员装饰器区分 API/浏览器请求
- 🟡 消息分页支持 (`before_id` 参数)
- 🟡 在线状态实时更新（WebSocket connect/disconnect）
- 🟡 侧边栏搜索过滤

**视觉重构**
- 🎨 全新靛蓝色配色方案，现代简洁风格
- 🎨 登录页渐变 logo + 居中卡片 + 入场动画
- 🎨 聊天页面重新设计（搜索、图标、气泡圆角）
- 🎨 管理后台新增统计卡片 + 卡片化表格
- 🎨 所有静态资源本地化，秒开无 CDN 依赖

**代码质量**
- 🟢 DatabaseConnection 上下文管理器，自动 commit/rollback
- 🟢 去掉 sys.stdout 重编码，改用 logging 模块
- 🟢 依赖版本宽松化（>= 替代 ==）
- 🟢 新增 python-dotenv + APScheduler 依赖
- 🟢 新增 .env.example 环境变量模板
- 🟢 数据库外键约束开启
- 🟢 更多索引优化

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

---

## 🐛 已知问题

1. **集群支持** — 当前版本不支持多服务器部署（Socket.IO 房间）
2. **消息搜索** — 暂不支持消息搜索功能
3. **消息撤回** — 暂不支持消息撤回

---

## 📄 许可证

MIT License

---

## 👥 开发团队

- **开发者**: NotJustSRE
- **GitHub**: https://github.com/zhouyaya100
