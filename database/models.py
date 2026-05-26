"""
database/models.py — SQL-схема базы данных
Содержит DDL-запросы для создания таблиц
"""

# SQL для создания всех таблиц
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY,
    username         TEXT,
    full_name        TEXT,
    registered_at    DATETIME DEFAULT (datetime('now')),
    subscription_type TEXT CHECK(subscription_type IN ('month', '3months', 'forever') OR subscription_type IS NULL),
    subscription_end  DATETIME,
    total_paid       REAL DEFAULT 0.0,
    is_active_subscriber BOOLEAN DEFAULT 0,
    channel_member   BOOLEAN DEFAULT 0,
    last_message_id  INTEGER,
    notified_5d      BOOLEAN DEFAULT 0,
    notified_3d      BOOLEAN DEFAULT 0,
    notified_1d      BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    amount          REAL NOT NULL,
    currency        TEXT DEFAULT 'USD',
    payment_system  TEXT NOT NULL,
    invoice_id      TEXT,
    pay_url         TEXT,
    status          TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'paid', 'expired', 'failed')),
    subscription_type TEXT,
    created_at      DATETIME DEFAULT (datetime('now')),
    paid_at         DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_invoice_id ON payments(invoice_id);
CREATE INDEX IF NOT EXISTS idx_users_subscription_end ON users(subscription_end);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active_subscriber);
"""