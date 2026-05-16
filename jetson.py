import os
import sys
import json
import queue
import time
import datetime
import threading
import requests
import feedparser
import re
import sounddevice as sd
from num2words import num2words
from vosk import Model, KaldiRecognizer
import subprocess

# --- НАСТРОЙКИ ---
PIPER_MODEL = "synthModel/mari.onnx"
PIPER_CONFIG = "synthModel/mari.onnx.json"
API_WEATHER_KEY = "a16151d6d074f7a37a032f50f98a760c"
CITY = "Novosibirsk"
NEWS_RSS_URL = "https://lenta.ru/rss/news"

print("Загрузка Vosk...")
vosk_model = Model("model")
rec = KaldiRecognizer(vosk_model, 16000)

# --- КЛАСС БЫСТРОГО СИНТЕЗА ---
class FastPiper:
    def __init__(self, piper_path="./piper/piper", model_path=PIPER_MODEL, config_path=PIPER_CONFIG):
        print("⏳ Загрузка модели Piper в оперативную память (один раз)...")
        
        # Запускаем piper в фоне в режиме потока
        self.piper_proc = subprocess.Popen(
            [
                piper_path, 
                "--model", model_path, 
                "--config", config_path,
                "--length_scale", "1.1", 
                "--output_raw"
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        
        # Сразу перенаправляем поток аудиоданных в ALSA (aplay)
        # Параметры aplay (22050 Hz, 16-bit) обычно подходят для большинства onnx моделей Piper
        self.aplay_proc = subprocess.Popen(
            ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-c", "1", "-q"],
            stdin=self.piper_proc.stdout,
            stderr=subprocess.DEVNULL
        )
        print("✅ Piper CLI готов к мгновенной работе")

    def speak(self, text):
        clean_text = text.replace('\n', ' ')
        # Отправляем текст и символ переноса строки, чтобы начать генерацию
        self.piper_proc.stdin.write((clean_text + "\n").encode('utf-8'))
        self.piper_proc.stdin.flush()


# --- ЛОГИКА АССИСТЕНТА ---
class LeraBrain:
    def __init__(self, tts_queue):
        self.name = "лера"
        self.tts_queue = tts_queue
        self.alarms = []
        self.timers = {}
        self.listening_mode = False

    def declension(self, n, one, two, five):
        n = abs(n) % 100
        if 11 <= n <= 19: return five
        n %= 10
        if n == 1: return one
        if 2 <= n <= 4: return two
        return five

    def get_time(self):
        now = datetime.datetime.now()
        h = now.hour
        m = now.minute
        if m == 0:
            return f"Сейчас {num2words(h, lang='ru')} часов ровно."
        elif m < 10:
            return f"Сейчас {num2words(h, lang='ru')} ноль {num2words(m, lang='ru')}."
        else:
            return f"Сейчас {num2words(h, lang='ru')} {num2words(m, lang='ru')}."

    def get_weather(self):
        url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_WEATHER_KEY}&units=metric&lang=ru"
        try:
            res = requests.get(url, timeout=5).json()
            temp = int(res['main']['temp'])
            desc = res['weather'][0]['description']
            return f"В Новосибирске сейчас {temp} {self.declension(temp, 'градус', 'градуса', 'градусов')}, {desc}."
        except:
            return "Не удалось узнать погоду."

    def get_news(self):
        try:
            feed = feedparser.parse(NEWS_RSS_URL)
            if not feed.entries:
                return "Новостей нет."
            titles = [e.title for e in feed.entries[:3]]
            news = "Последние новости. " + ". ".join(titles)
            return news.replace('"', '').replace("«", "").replace("»", "")
        except:
            return "Не удалось загрузить новости."

    def words_to_numbers(self, text):
        num_dict = {
            'ноль': 0, 'один': 1, 'одну': 1, 'одна': 1, 'два': 2, 'две': 2, 'три': 3, 'четыре': 4,
            'пять': 5, 'шесть': 6, 'семь': 7, 'восемь': 8, 'девять': 9, 'десять': 10,
            'одиннадцать': 11, 'двенадцать': 12, 'тринадцать': 13, 'четырнадцать': 14,
            'пятнадцать': 15, 'шестнадцать': 16, 'семнадцать': 17, 'восемнадцать': 18,
            'девятнадцать': 19, 'двадцать': 20, 'тридцать': 30, 'сорок': 40,
            'пятьдесят': 50, 'шестьдесят': 60
        }
        words = text.split()
        nums = []
        current = 0
        is_parsing = False
        for w in words:
            if w in num_dict:
                val = num_dict[w]
                if not is_parsing:
                    current = val
                    is_parsing = True
                else:
                    if current >= 20 and val < 10:
                        current += val
                    else:
                        nums.append(current)
                        current = val
            else:
                if is_parsing:
                    nums.append(current)
                    is_parsing = False
        if is_parsing:
            nums.append(current)
        return nums

    def start_timer(self, minutes):
        if minutes in self.timers:
            self.timers[minutes].cancel()
        t = threading.Timer(minutes * 60, self._timer_end, [minutes])
        self.timers[minutes] = t
        t.start()
        return f"Таймер на {minutes} {self.declension(minutes, 'минуту', 'минуты', 'минут')} запущен."

    def _timer_end(self, minutes):
        self.tts_queue.put(f"Таймер на {minutes} минут завершён!")
        self.timers.pop(minutes, None)

    def cancel_timer(self, text):
        nums = self.words_to_numbers(text)
        if nums:
            m = nums[0]
            if m in self.timers:
                self.timers[m].cancel()
                del self.timers[m]
                return f"Таймер на {m} минут отменён."
            return f"Таймер на {m} минут не найден."
        if len(self.timers) == 1:
            m, t = self.timers.popitem()
            t.cancel()
            return f"Таймер на {m} минут отменён."
        elif len(self.timers) > 1:
            return "У вас несколько таймеров. Уточните время."
        return "Активных таймеров нет."

    def set_alarm(self, time_str):
        match = re.search(r'(\d{1,2}):?(\d{2})?', time_str)
        if match:
            h = int(match.group(1))
            m = int(match.group(2)) if match.group(2) else 0
            alarm_time = f"{h:02d}:{m:02d}"
            self.alarms.append(alarm_time)
            return f"Будильник установлен на {alarm_time}."
        return "Не поняла время будильника."

    def cancel_alarms(self):
        count = len(self.alarms)
        self.alarms.clear()
        return f"Отменено {count} будильников." if count > 0 else "Будильников нет."

    def background_tasks_checker(self):
        while True:
            now_str = datetime.datetime.now().strftime("%H:%M")
            if now_str in self.alarms:
                self.tts_queue.put(f"Будильник на {now_str}!")
                self.alarms.remove(now_str)
            time.sleep(30)

    def handle(self, text):
        text = text.lower().strip()

        if not self.listening_mode:
            if self.name in text:
                self.listening_mode = True
                return "Да, слушаю."
            return None

        self.listening_mode = False

        if "будильник" in text and any(w in text for w in ["выключи", "отмени", "убери", "стоп"]):
            return self.cancel_alarms()

        if "таймер" in text and any(w in text for w in ["выключи", "отмени", "убери", "стоп"]):
            return self.cancel_timer(text)

        if "погода" in text: return self.get_weather()
        if "новости" in text: return self.get_news()
        if "время" in text or "час" in text or "времени" in text: return self.get_time()

        if "таймер" in text:
            nums = self.words_to_numbers(text)
            if nums: return self.start_timer(nums[0])
            return "На сколько минут поставить таймер?"

        if "будильник" in text:
            nums = self.words_to_numbers(text)
            if nums:
                time_str = f"{nums[0]:02d}" + (f":{nums[1]:02d}" if len(nums) > 1 else ":00")
                return self.set_alarm(time_str)

        if any(w in text for w in ["свет", "ламп", "розетк"]):
            if "включи" in text: return "Свет включён."
            if "выключи" in text: return "Свет выключен."

        return "Не поняла команду."


# --- ФУНКЦИЯ ВОСПРОИЗВЕДЕНИЯ ---
def synth_and_say(text):
    if not text:
        return

    text = re.sub(r'\d+', lambda m: num2words(int(m.group()), lang='ru'), text)
    text = text.replace("-", " минус ")

    print(f"Лера говорит: {text}")

    try:
        # Отправляем текст в фоновый процесс (мгновенный старт)
        voice.speak(text)
        
        # Умная пауза: Рассчитываем примерное время звучания (в среднем 12 символов в секунду)
        # Добавляем 0.5 сек запаса, чтобы микрофон не включился на последнем слове
        estimated_duration = max(1.0, len(text) / 12.0)
        time.sleep(estimated_duration + 0.5)

    except Exception as e:
        print(f"Ошибка Piper: {e}")


# --- ИНИЦИАЛИЗАЦИЯ ---
data_queue = queue.Queue()
tts_queue = queue.Queue()
brain = LeraBrain(tts_queue)

# Запускаем движок Piper
voice = FastPiper()

threading.Thread(target=brain.background_tasks_checker, daemon=True).start()

def callback(indata, frames, time, status):
    data_queue.put(bytes(indata))

print("\nЛера запущена. Говорите 'Лера' для активации.\n")

# --- ГЛАВНЫЙ ЦИКЛ ---
with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=callback) as stream:
    while True:
        # 1. Проверяем фоновые сообщения (таймеры/будильники)
        try:
            bg_message = tts_queue.get_nowait()
            stream.stop()
            try: hw.set_led("SPEAK") 
            except: pass
            
            synth_and_say(bg_message)
            
            try: hw.set_led("IDLE")
            except: pass
            stream.start()
        except queue.Empty:
            pass

        # 2. Слушаем микрофон
        try:
            data = data_queue.get(timeout=0.1)
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                recognized = res.get("text", "").strip()

                if recognized:
                    print(f"Распознано: {recognized}")
                    try: hw.set_led("LISTEN")
                    except: pass
                    
                    response = brain.handle(recognized)
                    if response:
                        stream.stop()
                        try: hw.set_led("SPEAK")
                        except: pass
                        
                        synth_and_say(response)
                        
                        try: hw.set_led("IDLE")
                        except: pass
                        stream.start()
        except queue.Empty:
            continue
