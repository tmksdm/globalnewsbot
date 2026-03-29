"""
Одноразовый скрипт: переносит существующие публикации в таблицу счётчиков.
Запустить один раз: python migrate_counts.py
"""
from app.db import get_connection, init_db

init_db()

conn = get_connection()
cursor = conn.cursor()

# Проверяем, не мигрировали ли уже
cursor.execute('SELECT COUNT(*) as cnt FROM publish_counts')
if cursor.fetchone()['cnt'] > 0:
    print("⚠️ Таблица publish_counts уже содержит данные. Пропускаю.")
    conn.close()
    exit()

# Переносим из processed_news
cursor.execute('SELECT project_name, score, published_at FROM processed_news')
rows = cursor.fetchall()

for row in rows:
    cursor.execute('''
        INSERT INTO publish_counts (project_name, score, published_at)
        VALUES (?, ?, ?)
    ''', (row['project_name'], row['score'], row['published_at']))

conn.commit()
conn.close()
print(f"✅ Перенесено {len(rows)} записей в publish_counts.")
