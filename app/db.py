import sqlite3
import datetime

DB_NAME = "news.db"

def init_db():
    """Создает таблицу и мигрирует схему при необходимости."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Создаем таблицу, если нет
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT DEFAULT 'default', -- НОВОЕ ПОЛЕ
            content_hash TEXT, 
            original_text TEXT,
            summary TEXT,
            score INTEGER,
            source_link TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # == МИГРАЦИЯ (для старой базы) ==
    # Проверяем, есть ли колонка project_name
    cursor.execute("PRAGMA table_info(processed_news)")
    columns = [info[1] for info in cursor.fetchall()]
    if "project_name" not in columns:
        print("🛠 Обновляю структуру базы данных (добавляю project_name)...")
        cursor.execute("ALTER TABLE processed_news ADD COLUMN project_name TEXT DEFAULT 'default'")
    
    conn.commit()
    conn.close()

def add_news(project_name, content_hash, original_text, summary, score, source_link):
    """Сохраняет новость с привязкой к проекту."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO processed_news (project_name, content_hash, original_text, summary, score, source_link)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (project_name, content_hash, original_text, summary, score, source_link))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"❌ DB Error: {e}")
        return False
    finally:
        conn.close()

def is_exists(project_name, content_hash):
    """Проверяет хеш ТОЛЬКО в рамках текущего проекта."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Ищем совпадение И хеша, И имени проекта
    cursor.execute('''
        SELECT 1 FROM processed_news 
        WHERE content_hash = ? AND project_name = ?
    ''', (content_hash, project_name))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def get_recent_news(project_name, days=2):
    """Достает историю ТОЛЬКО для текущего проекта."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    limit_date = datetime.datetime.now() - datetime.timedelta(days=days)
    
    cursor.execute('''
        SELECT summary, original_text 
        FROM processed_news 
        WHERE published_at > ? AND project_name = ?
    ''', (limit_date, project_name))
    rows = cursor.fetchall()
    conn.close()
    return rows

def cleanup_old_records(days=5):
    """Чистит старье (общая чистка)."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    limit_date = datetime.datetime.now() - datetime.timedelta(days=days)
    cursor.execute('DELETE FROM processed_news WHERE published_at < ?', (limit_date,))
    conn.commit()
    conn.close()

init_db()
