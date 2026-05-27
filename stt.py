"""
Модуль распознавания речи (STT) на базе Vosk
"""
import json
from vosk import Model, KaldiRecognizer
from config import VOSK_MODEL_PATH, SAMPLE_RATE


class SpeechRecognizer:
    """Класс для распознавания речи через Vosk"""
    
    def __init__(self, model_path=None):
        model_path = model_path or VOSK_MODEL_PATH
        print("Загрузка Vosk...")
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, SAMPLE_RATE)
        print("Vosk загружен")

    def process_audio(self, audio_data):
        """Обработать порцию аудио данных"""
        if self.recognizer.AcceptWaveform(audio_data):
            result = json.loads(self.recognizer.Result())
            return result.get("text", "").strip()
        return None

    def get_final_result(self):
        """Получить финальный результат распознавания"""
        result = json.loads(self.recognizer.FinalResult())
        return result.get("text", "").strip()
