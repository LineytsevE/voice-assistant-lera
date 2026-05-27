"""
Конфигурация голосового ассистента Лера
"""

# Piper TTS настройки
PIPER_MODEL = "synthModel/mari.onnx"
PIPER_CONFIG = "synthModel/mari.onnx.json"
PIPER_PATH = "./piper/piper"
PIPER_LENGTH_SCALE = "1.1"

# Настройки погоды
API_WEATHER_KEY = "a16151d6d074f7a37a032f50f98a760c"
CITY = "Novosibirsk"

# Настройки новостей
NEWS_RSS_URL = "https://lenta.ru/rss/news"

# Настройки Tuya (умная розетка)
TUYA_DEVICE_ID = 'bf92458fb773b88fcdl2vp'
TUYA_IP = '192.168.0.20'
TUYA_LOCAL_KEY = r"""Jlxs3u)e>Z-n:dNe"""
TUYA_VERSION = 3.5
TUYA_TIMEOUT = 2

# Настройки аудио
SAMPLE_RATE = 16000
BLOCK_SIZE = 8000
AUDIO_CHANNELS = 1

# Настройки Vosk STT
VOSK_MODEL_PATH = "model"

# Настройки ассистента
ASSISTANT_NAME = "лера"
SPEECH_RATE = 12  # символов в секунду для расчета длительности
SPEECH_DELAY = 0.5  # дополнительная пауза после речи
