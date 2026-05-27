"""
Модуль текст-в-речь (TTS) на базе Piper
"""
import subprocess
import re
import time
from num2words import num2words
from config import (
    PIPER_PATH, PIPER_MODEL, PIPER_CONFIG, 
    PIPER_LENGTH_SCALE, SPEECH_RATE, SPEECH_DELAY
)


class FastPiper:
    """Класс для быстрого синтеза речи через Piper CLI"""
    
    def __init__(self, piper_path=None, model_path=None, config_path=None):
        piper_path = piper_path or PIPER_PATH
        model_path = model_path or PIPER_MODEL
        config_path = config_path or PIPER_CONFIG
        
        print("⏳ Загрузка модели Piper в оперативную память (один раз)...")
        
        # Запускаем piper в фоне в режиме потока
        self.piper_proc = subprocess.Popen(
            [
                piper_path, 
                "--model", model_path, 
                "--config", config_path,
                "--length_scale", PIPER_LENGTH_SCALE, 
                "--output_raw"
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        
        # Сразу перенаправляем поток аудиоданных в ALSA (aplay)
        self.aplay_proc = subprocess.Popen(
            ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-c", "1", "-q"],
            stdin=self.piper_proc.stdout,
            stderr=subprocess.DEVNULL
        )
        print("✅ Piper CLI готов к мгновенной работе")

    def speak(self, text):
        """Синтезировать и воспроизвести текст"""
        clean_text = text.replace('\n', ' ')
        self.piper_proc.stdin.write((clean_text + "\n").encode('utf-8'))
        self.piper_proc.stdin.flush()

    def close(self):
        """Закрыть процессы"""
        try:
            self.piper_proc.terminate()
            self.aplay_proc.terminate()
        except Exception:
            pass


def prepare_text(text):
    """Подготовить текст для синтеза (заменить цифры на слова)"""
    text = re.sub(r'\d+', lambda m: num2words(int(m.group()), lang='ru'), text)
    text = text.replace("-", " минус ")
    return text


def synth_and_say(voice_engine, text):
    """Синтезировать и воспроизвести текст с паузой"""
    if not text:
        return

    text = prepare_text(text)
    print(f"Лера говорит: {text}")

    try:
        voice_engine.speak(text)
        
        # Умная пауза: Рассчитываем примерное время звучания
        estimated_duration = max(1.0, len(text) / SPEECH_RATE)
        time.sleep(estimated_duration + SPEECH_DELAY)

    except Exception as e:
        print(f"Ошибка Piper: {e}")
