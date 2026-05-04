-- indusmapk 用戶標籤系統
-- 跑法：wrangler d1 execute indusmapk-admin --file=db/migrations/0002_user_tags.sql
--      （也可加 --remote 部署到線上 D1）
--
-- 設計：
--   - tags                : 標籤主表（name 全站唯一、可上色）
--   - user_tags           : 用戶 ↔ 標籤的多對多 junction
--   - 標籤刪除 → CASCADE 清除 user_tags 關聯
--   - 用戶刪除 → 同上（雖然系統不開放硬刪，預防）

-- ─────────────────────────────────────────────────────────────────
-- tags：標籤主表
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  color TEXT NOT NULL DEFAULT 'cyan'
    CHECK(color IN ('cyan','magenta','violet','emerald','amber','rose','sky','lime')),
  description TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);

-- ─────────────────────────────────────────────────────────────────
-- user_tags：用戶 ↔ 標籤關聯
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_tags (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  assigned_by INTEGER REFERENCES users(id),
  assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_user_tags_user ON user_tags(user_id);
CREATE INDEX IF NOT EXISTS idx_user_tags_tag ON user_tags(tag_id);
