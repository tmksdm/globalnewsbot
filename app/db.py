import sqlite3
import datetime
from datetime import timezone, timedelta

DB_NAME = "news.db"


def get_connection():
    """Возвращает соединение с базой данных."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Создает все таблицы и мигрирует схему при необходимости."""
    conn = get_connection()
    cursor = conn.cursor()

    # --- Таблица новостей (уже существует) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT DEFAULT 'default',
            content_hash TEXT,
            original_text TEXT,
            summary TEXT,
            score INTEGER,
            source_link TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Миграция: добавляем project_name если его нет (для старых баз)
    cursor.execute("PRAGMA table_info(processed_news)")
    columns = [info[1] for info in cursor.fetchall()]
    if "project_name" not in columns:
        print("🛠 Миграция: добавляю project_name в processed_news...")
        cursor.execute("ALTER TABLE processed_news ADD COLUMN project_name TEXT DEFAULT 'default'")

    # --- Таблица проектов ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            source_folder_id INTEGER NOT NULL,
            target_channel_id INTEGER NOT NULL,
            min_score INTEGER DEFAULT 7,
            prompt_type TEXT DEFAULT 'default',
            is_active INTEGER DEFAULT 1,
            test_mode INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute("PRAGMA table_info(projects)")
    proj_columns = [info[1] for info in cursor.fetchall()]
    if "test_mode" not in proj_columns:
        print("🛠 Миграция: добавляю test_mode в projects...")
        cursor.execute("ALTER TABLE projects ADD COLUMN test_mode INTEGER DEFAULT 0")

    # --- Таблица промптов ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_type TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            criteria TEXT NOT NULL,
            summary_style TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # --- НОВОЕ: Таблица уже виденных новостей (для экономии AI-запросов) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seen_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Индекс для быстрого поиска
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_seen_news_hash
        ON seen_news (project_name, content_hash)
    ''')

    conn.commit()
    conn.close()


# ========================
# ФУНКЦИИ ДЛЯ НОВОСТЕЙ
# ========================

def add_news(project_name, content_hash, original_text, summary, score, source_link):
    """Сохраняет новость с привязкой к проекту."""
    try:
        conn = get_connection()
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 1 FROM processed_news
        WHERE content_hash = ? AND project_name = ?
    ''', (content_hash, project_name))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


# --- НОВОЕ: Функции для seen_news ---

def is_seen(project_name, content_hash):
    """Проверяет, видели ли мы уже эту новость (отправляли ли в AI)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 1 FROM seen_news
        WHERE content_hash = ? AND project_name = ?
    ''', (content_hash, project_name))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def mark_as_seen(project_name, hashes):
    """Помечает список хешей как виденные. hashes — список строк."""
    if not hashes:
        return
    conn = get_connection()
    cursor = conn.cursor()
    for h in hashes:
        cursor.execute('''
            INSERT OR IGNORE INTO seen_news (project_name, content_hash)
            VALUES (?, ?)
        ''', (project_name, h))
    conn.commit()
    conn.close()


def cleanup_seen_news(days=3):
    """Удаляет старые записи из seen_news, чтобы таблица не росла бесконечно."""
    conn = get_connection()
    cursor = conn.cursor()
    limit_date = datetime.datetime.now() - datetime.timedelta(days=days)
    cursor.execute('DELETE FROM seen_news WHERE seen_at < ?', (limit_date,))
    conn.commit()
    conn.close()


def get_recent_news(project_name, days=2):
    """Достает историю ТОЛЬКО для текущего проекта."""
    conn = get_connection()
    cursor = conn.cursor()
    limit_date = datetime.datetime.now() - datetime.timedelta(days=days)
    cursor.execute('''
        SELECT summary, original_text
        FROM processed_news
        WHERE published_at > ? AND project_name = ?
    ''', (limit_date, project_name))
    rows = cursor.fetchall()
    conn.close()
    return [(row['summary'], row['original_text']) for row in rows]


def cleanup_old_records(days=5):
    """Чистит старые записи."""
    conn = get_connection()
    cursor = conn.cursor()
    limit_date = datetime.datetime.now() - datetime.timedelta(days=days)
    cursor.execute('DELETE FROM processed_news WHERE published_at < ?', (limit_date,))
    conn.commit()
    conn.close()


# ========================
# ФУНКЦИИ ДЛЯ ПРОЕКТОВ
# ========================

def get_all_projects():
    """Возвращает все проекты из базы."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects ORDER BY id')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_active_projects():
    """Возвращает только активные проекты (is_active=1)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE is_active = 1 ORDER BY id')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_project_by_id(project_id):
    """Возвращает один проект по ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def add_project(name, source_folder_id, target_channel_id, min_score=7, prompt_type='default'):
    """Добавляет новый проект."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO projects (name, source_folder_id, target_channel_id, min_score, prompt_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, source_folder_id, target_channel_id, min_score, prompt_type))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        print(f"⚠️ Проект с именем '{name}' уже существует.")
        return False
    finally:
        conn.close()


def update_project(project_id, **kwargs):
    """
    Обновляет поля проекта.
    Пример: update_project(1, min_score=8, is_active=0)
    """
    allowed_fields = ['name', 'source_folder_id', 'target_channel_id',
                      'min_score', 'prompt_type', 'is_active', 'test_mode']
    updates = []
    values = []
    for key, value in kwargs.items():
        if key in allowed_fields:
            updates.append(f"{key} = ?")
            values.append(value)

    if not updates:
        return False

    values.append(project_id)
    sql = f"UPDATE projects SET {', '.join(updates)} WHERE id = ?"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, values)
    conn.commit()
    conn.close()
    return True


# ========================
# ФУНКЦИИ ДЛЯ ПРОМПТОВ
# ========================

def get_all_prompts():
    """Возвращает все промпты из базы."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM prompts ORDER BY id')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_prompt_by_type(prompt_type):
    """Возвращает один промпт по типу."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM prompts WHERE prompt_type = ?', (prompt_type,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def add_prompt(prompt_type, role, criteria, summary_style):
    """Добавляет новый промпт."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO prompts (prompt_type, role, criteria, summary_style)
            VALUES (?, ?, ?, ?)
        ''', (prompt_type, role, criteria, summary_style))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        print(f"⚠️ Промпт с типом '{prompt_type}' уже существует.")
        return False
    finally:
        conn.close()


def update_prompt(prompt_type, role, criteria, summary_style):
    """Обновляет существующий промпт."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE prompts SET role = ?, criteria = ?, summary_style = ?, updated_at = CURRENT_TIMESTAMP
        WHERE prompt_type = ?
    ''', (role, criteria, summary_style, prompt_type))
    conn.commit()
    conn.close()
    return True


# ========================
# ФУНКЦИИ ДЛЯ СТАТИСТИКИ (веб-панель)
# ========================

def get_stats(project_name=None):
    """
    Возвращает статистику: сегодня, за неделю, всего, средний score.
    Если project_name=None — по всем проектам.
    Время считается по Владивостоку (UTC+10).
    """
    conn = get_connection()
    cursor = conn.cursor()

    tz_vlad = timezone(timedelta(hours=10))
    now_vlad = datetime.datetime.now(tz_vlad)
    today = now_vlad.date().isoformat()
    week_ago = (now_vlad.date() - datetime.timedelta(days=7)).isoformat()

    where = ""
    params = []
    if project_name:
        where = "WHERE project_name = ?"
        params = [project_name]

    # Всего
    cursor.execute(f'SELECT COUNT(*) as cnt FROM processed_news {where}', params)
    total = cursor.fetchone()['cnt']

    # Сегодня
    today_where = "WHERE date(published_at, '+10 hours') = ?"
    if project_name:
        today_where += " AND project_name = ?"
    today_params = [today] if not project_name else [today, project_name]
    cursor.execute(f'SELECT COUNT(*) as cnt FROM processed_news {today_where}', today_params)
    today_count = cursor.fetchone()['cnt']

    # За неделю
    week_where = "WHERE date(published_at, '+10 hours') >= ?"
    if project_name:
        week_where += " AND project_name = ?"
    week_params = [week_ago] if not project_name else [week_ago, project_name]
    cursor.execute(f'SELECT COUNT(*) as cnt FROM processed_news {week_where}', week_params)
    week_count = cursor.fetchone()['cnt']

    # Средний score
    cursor.execute(f'SELECT AVG(score) as avg_score FROM processed_news {where}', params)
    avg_row = cursor.fetchone()
    avg_score = round(avg_row['avg_score'], 1) if avg_row['avg_score'] else 0

    conn.close()
    return {
        'total': total,
        'today': today_count,
        'week': week_count,
        'avg_score': avg_score
    }


def get_published_news(project_name=None, date_from=None, date_to=None, limit=50, offset=0):
    """Возвращает список опубликованных новостей с фильтрацией."""
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []

    if project_name:
        conditions.append("project_name = ?")
        params.append(project_name)
    if date_from:
        conditions.append("date(published_at) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("date(published_at) <= ?")
        params.append(date_to)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    cursor.execute(f'''
        SELECT *, datetime(published_at, '+10 hours') as published_at_local
        FROM processed_news
        {where}
        ORDER BY published_at DESC
        LIMIT ? OFFSET ?
    ''', params + [limit, offset])
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_project_names():
    """Возвращает список уникальных имен проектов из таблицы новостей."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT project_name FROM processed_news ORDER BY project_name')
    rows = cursor.fetchall()
    conn.close()
    return [row['project_name'] for row in rows]


# Инициализация БД при импорте
init_db()
