# 数据库优化策略

## 存储优化

### 未读消息记录设计

**核心原则**：只记录状态，不存储内容

```sql
-- 每个用户 + 群组只保留 1 条记录
CREATE TABLE unread_group_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    last_read_message_id INTEGER DEFAULT 0,  -- 只存 ID，4-8 字节
    last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, group_id)  -- 唯一约束，自动覆盖旧记录
);

-- 每个用户 + 发送者只保留 1 条记录
CREATE TABLE unread_private_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    last_read_message_id INTEGER DEFAULT 0,
    last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, sender_id)
);
```

### 空间占用估算

假设服务器有：
- 100 个用户
- 平均每人加入 10 个群组
- 平均每人有 20 个联系人

**未读记录表大小**：
- `unread_group_messages`: 100 用户 × 10 群组 = 1,000 条记录
- `unread_private_messages`: 100 用户 × 20 联系人 = 2,000 条记录
- 每条记录约 50 字节 → 总共约 150KB

**对比**：
- ❌ 存储每条未读消息：100 用户 × 100 消息/天 × 10 天 = 100,000 条
- ✅ 只存最后已读 ID：3,000 条记录
- **空间节省**: 97%+

## 自动清理策略

### 定时清理任务（每天凌晨 2 点）

```python
def cleanup_expired_messages():
    # 1. 删除过期消息（10 天前）
    DELETE FROM messages WHERE expires_at < ?
    DELETE FROM private_messages WHERE expires_at < ?
    
    # 2. 清理无效未读记录
    # - 用户已退出的群组
    # - 用户已删除的记录
```

### 手动清理 API

```
POST /api/clear_unread
```

一键清空所有未读记录（可选功能）

## 查询优化

### 索引设计

```sql
-- 加速未读消息计数查询
CREATE INDEX idx_private_messages_read ON private_messages(receiver_id, is_read);

-- 加速群组消息查询
CREATE INDEX idx_messages_group ON messages(group_id, created_at);
```

### 未读数量查询优化

```sql
-- 高效查询未读数量（利用 is_read 标记）
SELECT sender_id, COUNT(*) as unread_count
FROM private_messages
WHERE receiver_id = ? AND is_read = 0
GROUP BY sender_id
```

## 性能监控

### 数据库大小检查

```sql
-- 检查表大小
SELECT 
    name,
    pgsize_and_unused(name) as size
FROM sqlite_dbpage
GROUP BY name;
```

### 建议阈值

- 数据库文件 > 100MB: 考虑归档旧消息
- 单表记录 > 100 万：考虑分表或分页
- 查询时间 > 1 秒：检查索引

## 最佳实践

1. **定期 VACUUM**: 每月执行一次 `VACUUM` 回收空间
2. **消息保留期**: 默认 10 天，可根据需求调整
3. **未读记录**: 自动清理，无需手动干预
4. **文件存储**: 大文件单独存放，数据库只存路径

---

**更新日期**: 2026-03-17
**版本**: v1.0.1
