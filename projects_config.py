# Здесь мы задаем настройки для каждого "бота" (проекта)
# name — нужно для базы данных, чтобы отличать историю постов одного канала от другого.

PROJECTS = [
    {
        "name": "economic_main",           # Уникальное имя проекта (латиницей, без пробелов)
        "source_folder_id": 6,             # ID папки с источниками (из setup_telegram.py)
        "target_channel_id": -1001720250424, # ID твоего канала, куда постить
        "min_score": 7,                    # Минимальная оценка нейросети (можно менять для разных каналов)
        "prompt_type": "default"           # Задел на будущее (если захочешь разные стили)
    },
    # Пример второго проекта (раскомментируй и заполни, когда будет нужно)
    {
        "name": "primlenta",
        "source_folder_id": 4,        
        "target_channel_id": -1002518512643,
        "min_score": 7,                
        "prompt_type": "primlentaprompt"       
    },

            {
        "name": "ussurlenta",
        "source_folder_id": 2,        
        "target_channel_id": -1002846373339,
        "min_score": 7,                
        "prompt_type": "ussurlentaprompt"       
    },
]
