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
import numpy as np
from num2words import num2words
from vosk import Model, KaldiRecognizer
import io
import wave

# ====================== НАСТРОЙКИ ======================
PIPER_MODEL_PATH = r"synthModel/mari.onnx"
PIPER_CONFIG_PATH = r"synthModel/mari.onnx.json"

API_WEATHER_KEY = "a16151d6d074f7a37a032f50f98a760c"
CITY = "Novosibirsk"
NEWS_RSS_URL = "https://lenta.ru/rss/news"

# ====================== ИНИЦИАЛИЗАЦИЯ ======================
print("Инициализация Vosk...")
vosk_model = Model("model")
rec = KaldiRecognizer(vosk_model, 16000)

print("Загрузка модели Piper TTS...")
try:
    from piper.voice import PiperVoice
    voice = PiperVoice.load(PIPER_MODEL_PATH, config_path=PIPER_CONFIG_PATH)
    print("Piper TTS успешно загружен!")
except Exception as e:
    print(f"Ошибка загрузки Piper: {e}")
    sys.exit(1)

# ====================== HARDWARE ======================
class Hardware:
    def __init__(self):
        self.LED_R, self.LED_G, self.LED_B = 11, 13, 15
        self.RELAY_LIGHT = 16
        self.HAS_GPIO = False
        try:
            import Jetson.GPIO as GPIO
            GPIO.setmode(GPIO.BOARD)
            GPIO.setup([self.LED_R, self.LED_G, self.LED_B, self.RELAY_LIGHT], GPIO.OUT, initial=GPIO.LOW)
            self.GPIO = GPIO
            self.HAS_GPIO = True
            print("Jetson.GPIO инициализирован")
        except:
            print("Jetson.GPIO не найден — режим эмуляции")

    def set_led(self, mode):
        if not self.HAS_GPIO: return
        self.GPIO.output((self.LED_R, self.LED_G, self.LED_B), self.GPIO.LOW)
        if mode == "LISTEN":
            self.GPIO.output(self.LED_B, self.GPIO.HIGH)
        elif mode == "SPEAK":
            self.GPIO.output(self.LED_G, self.GPIO.HIGH)
        elif mode == "ERROR":
            self.GPIO.output(self.LED_R, self.GPIO.HIGH)


hw = Hardware()


# ====================== МОЗГ ======================
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
            'ноль':0,'один':1,'одну':1,'одна':1,'два':2,'две':2,'три':3,'четыре':4,
            'пять':5,'шесть':6,'семь':7,'восемь':8,'девять':9,'десять':10,
            'одиннадцать':11,'двенадцать':12,'тринадцать':13,'четырнадцать':14,
            'пятнадцать':15,'шестнадцать':16,'семнадцать':17,'восемнадцать':18,
            'девятнадцать':19,'двадцать':20,'тридцать':30,'сорок':40,
            'пятьдесят':50,'шестьдесят':60
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
        return f"Таймер на {minutes} минут запущен."

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
        return "Таймер не найден."

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

        if "будильник" in text and any(w in text for w in ["выключи", "отмени", "убери"]):
            return self.cancel_alarms()

        if "таймер" in text and any(w in text for w in ["выключи", "отмени", "убери"]):
            return self.cancel_timer(text)

        if "погода" in text: return self.get_weather()
        if "новости" in text: return self.get_news()
        if "время" in text or "час" in text: return self.get_time()

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


# ====================== СИНТЕЗ РЕЧИ ======================
def synth_and_say(text):
    if not text:
        return

    text = re.sub(r'\d+', lambda m: num2words(int(m.group()), lang='ru'), text)
    text = text.replace("-", " минус ")

    print(f"Лера говорит: {text}")

    try:
        byte_io = io.BytesIO()
        with wave.open(byte_io, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)

        wav_bytes = byte_io.getvalue()
        audio_np = np.frombuffer(wav_bytes[44:], dtype=np.int16)

        if len(audio_np) > 0:
            sd.play(audio_np, samplerate=voice.config.sample_rate)
            sd.wait()
    except Exception as e:
        print(f"Ошибка синтеза: {e}")


# ====================== ЗАПУСК ======================
data_queue = queue.Queue()
tts_queue = queue.Queue()
brain = LeraBrain(tts_queue)

threading.Thread(target=brain.background_tasks_checker, daemon=True).start()

def callback(indata, frames, time, status):
    data_queue.put(bytes(indata))

print("\nЛера запущена. Говорите 'Лера' для активации.\n")

with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=callback) as stream:
    while True:
        try:
            bg_message = tts_queue.get_nowait()
            stream.stop()
            hw.set_led("SPEAK")
            synth_and_say(bg_message)
            hw.set_led("IDLE")
            stream.start()
        except queue.Empty:
            pass

        try:
            data = data_queue.get(timeout=0.1)
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                recognized = res.get("text", "").strip()

                if recognized:
                    print(f"Распознано: {recognized}")
                    hw.set_led("LISTEN")
                    response = brain.handle(recognized)
                    if response:
                        stream.stop()
                        hw.set_led("SPEAK")
                        synth_and_say(response)
                        hw.set_led("IDLE")
                        stream.start()
        except queue.Empty:
            continue
