-- indusmapk 訂閱式會員系統 + 後台 — 初始 schema
-- 跑法：wrangler d1 execute indusmapk-admin --file=db/migrations/0001_init.sql

-- ─────────────────────────────────────────────────────────────────
-- users：5 級分權的用戶主表
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  google_id TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  name TEXT,
  picture TEXT,
  role TEXT NOT NULL DEFAULT 'member'
    CHECK(role IN ('member','premium','admin','super_admin')),
  role_expires_at TEXT,
  data_permissions TEXT,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_login_at TEXT,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK(status IN ('active','suspended'))
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_role_exp
  ON users(role_expires_at)
  WHERE role_expires_at IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────
-- audit_log：所有寫入操作的記錄
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  user_email TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  diff_summary TEXT,
  ip TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_user_time
  ON audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action_time
  ON audit_log(action, created_at DESC);

-- ─────────────────────────────────────────────────────────────────
-- access_rules：路徑訪問權限規則（super_admin 在後台維護）
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS access_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path_pattern TEXT NOT NULL,
  required_role TEXT NOT NULL
    CHECK(required_role IN ('guest','member','premium','admin')),
  comment TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_access_rules_active
  ON access_rules(active, path_pattern);

-- ─────────────────────────────────────────────────────────────────
-- Bootstrap：super_admin 列表
-- 各帳號首次用 OAuth 登入時，callback 會偵測 email 已存在 +
-- google_id 以 'PENDING' 開頭 → 自動 UPDATE google_id 綁定該 Google 帳號
-- google_id 必須 UNIQUE，所以多個 placeholder 用 _1 / _2 / ... 區分
-- ─────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO users (google_id, email, name, role)
VALUES ('PENDING_1', 'linliusan.claude0823@gmail.com', 'KK', 'super_admin');

INSERT OR IGNORE INTO users (google_id, email, name, role)
VALUES ('PENDING_2', 'gogostock1227@gmail.com', 'KK', 'super_admin');
