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
import torch
import sounddevice as sd
from num2words import num2words
from vosk import Model, KaldiRecognizer

API_WEATHER_KEY = "a16151d6d074f7a37a032f50f98a760c"
CITY = "Novosibirsk"
NEWS_RSS_URL = "https://lenta.ru/rss/news"

try:
    print("инит воск...")
    vosk_model = Model("model")
    rec = KaldiRecognizer(vosk_model, 16000)

    print("silero tts...")
    device = torch.device("cuda")
    torch.set_num_threads(2)
    tts_model, _ = torch.hub.load(repo_or_dir='snakers4/silero-models',
                                  model='silero_tts', language='ru', speaker='v4_ru')
    tts_model.to(device)
except Exception as e:
    print(f"ошибка: {e}")
    sys.exit()

try:
    import Jetson.GPIO as GPIO

    GPIO.setmode(GPIO.BOARD)
    HAS_GPIO = True
except (ImportError, ModuleNotFoundError):
    print("джетсон не найден работа в режиме жэмуляции")
    HAS_GPIO = False

class Hardware:
    def __init__(self):
        self.LED_R, self.LED_G, self.LED_B = 11, 13, 15
        self.RELAY_LIGHT = 16

        if HAS_GPIO:
            GPIO.setup([self.LED_R, self.LED_G, self.LED_B, self.RELAY_LIGHT], GPIO.OUT, initial=GPIO.LOW)
            self.light_status = False

    def set_led(self, mode):
        if not HAS_GPIO: return
        GPIO.output((self.LED_R, self.LED_G, self.LED_B), GPIO.LOW)
        if mode == "LISTEN":
            GPIO.output(self.LED_B, GPIO.HIGH)
        elif mode == "SPEAK":
            GPIO.output(self.LED_G, GPIO.HIGH)
        elif mode == "ERROR":
            GPIO.output(self.LED_R, GPIO.HIGH)

    def toggle_light(self, state=None):
        if not HAS_GPIO: return "Эмуляция: свет переключен."

        if state == "ON":
            self.light_status = True
            GPIO.output(self.RELAY_LIGHT, GPIO.HIGH)
            return "Свет включен."
        elif state == "OFF":
            self.light_status = False
            GPIO.output(self.RELAY_LIGHT, GPIO.LOW)
            return "Свет выключен."
        return "Не поняла, включить или выключить свет?"

class LeraBrain:
    def words_to_numbers(self, text):
        num_dict = {
            'ноль': 0, 'один': 1, 'одну': 1, 'одна': 1, 'два': 2, 'две': 2, 'три': 3,
            'четыре': 4, 'пять': 5, 'шесть': 6, 'семь': 7, 'восемь': 8, 'девять': 9,
            'десять': 10, 'одиннадцать': 11, 'двенадцать': 12, 'тринадцать': 13,
            'четырнадцать': 14, 'пятнадцать': 15, 'шестнадцать': 16, 'семнадцать': 17,
            'восемнадцать': 18, 'девятнадцать': 19, 'двадцать': 20, 'тридцать': 30,
            'сорок': 40, 'пятьдесят': 50, 'шестьдесят': 60
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
                    current = 0

        if is_parsing:
            nums.append(current)

        return nums
    def __init__(self, tts_queue):
        self.name = "лера"
        self.tts_queue = tts_queue
        self.alarms = []

    def get_time(self):
        now = datetime.datetime.now()
        return f"Сейчас {now.hour} {now.minute}..."
    def get_weather(self):
        url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_WEATHER_KEY}&units=metric&lang=ru"
        try:
            res = requests.get(url, timeout=5).json()
            temp = int(res['main']['temp'])
            desc = res['weather'][0]['description']
            return f"в новосибирске сейчас {temp} градусов, {desc}."
        except:
            return "не удалось узнать погоду."

    def get_news(self):
        try:
            feed = feedparser.parse(NEWS_RSS_URL)
            if not feed.entries:
                return "список новостей пуст."
            titles = [e.title for e in feed.entries[:3]]
            full_news = "последние новости. " + ". ".join(titles)
            full_news = full_news.replace('"', '').replace("'", "").replace("«", "").replace("»", "")

            return str(full_news)
        except Exception as e:
            print(f"ошибка рсс: {e}")
            return "не удалось загрузить новости."

    def start_timer(self, minutes):
        def timer_func():
            time.sleep(minutes * 60)
            self.tts_queue.put(f"таймер на {minutes} минут завершен!")
        threading.Thread(target=timer_func, daemon=True).start()
        return f"таймер запущен на {minutes} минут."

    def set_alarm(self, time_str):
        match = re.search(r'(\d{1,2}):(\d{2})', time_str)
        if match:
            h, m = match.groups()
            alarm_time = f"{int(h):02d}:{int(m):02d}"
            self.alarms.append(alarm_time)
            return f"будильник установлен на {alarm_time}."
        return "не поняла время будильника."

    def background_tasks_checker(self):
        while True:
            now_str = datetime.datetime.now().strftime("%H:%M")
            if now_str in self.alarms:
                self.tts_queue.put(f"будильник на {now_str}!")
                self.alarms.remove(now_str)
            time.sleep(30)

    def handle(self, text):
        text = text.lower()
        if "погода" in text:
            return self.get_weather()

        if "новости" in text:
            return self.get_news()

        if "время" in text or "час" in text:
            return self.get_time()

        if "таймер" in text:
            nums = self.words_to_numbers(text)
            if nums:
                return self.start_timer(nums[0])
            return "на сколько минут поставить таймер?"

        if "будильник" in text:
            nums = self.words_to_numbers(text)
            if len(nums) == 2:
                return self.set_alarm(f"{nums[0]:02d}:{nums[1]:02d}")
            elif len(nums) == 1:
                return self.set_alarm(f"{nums[0]:02d}:00")
            return "не поняла время будильника."

        if "свет" in text:
            if "включи" in text: return hw.toggle_light("ON")
            if "выключи" in text: return hw.toggle_light("OFF")
            return hw.toggle_light()
        return "я не понимаю, помогите"

def synth_and_say(text):
    if text is None:
        text = "ошибка"
    def replace_num(match):
        return num2words(int(match.group()), lang='ru')
    text = text.replace("-", "минус ")
    text = re.sub(r'\d+', replace_num, text)
    clean_text = "".join(c for c in text if c.isalpha() or c in " ,.!?:-")
    print(f"лера говорит: {clean_text}")
    try:
        audio = tts_model.apply_tts(text=clean_text, speaker='xenia', sample_rate=24000)
        sd.play(audio.numpy(), 24000)
        sd.wait()
    except Exception as e:
        print(f"ошибка ттс: {e}")

hw = Hardware()
data_queue = queue.Queue()
tts_queue = queue.Queue()
brain = LeraBrain(tts_queue)
threading.Thread(target=brain.background_tasks_checker, daemon=True).start()

def callback(indata, frames, time, status):
    data_queue.put(bytes(indata))

print("Жду голос лера + команда")
with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=callback) as stream:
    while True:
        try:
            bg_message = tts_queue.get_nowait()
            stream.stop()
            hw.set_led("SPEAK")
            synth_and_say(bg_message)
            with data_queue.mutex:
                data_queue.queue.clear()
            hw.set_led("IDLE")
            stream.start()
        except queue.Empty:
            pass
        try:
            data = data_queue.get(timeout=0.1)
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                recognized = res.get("text", "")

                if recognized and brain.name in recognized:
                    cmd = recognized.replace(brain.name, "").strip()
                    print(f"распознано: {cmd}")

                    hw.set_led("LISTEN")
                    response = brain.handle(cmd) if cmd else "слушаю......"

                    stream.stop()
                    hw.set_led("SPEAK")
                    synth_and_say(response)

                    with data_queue.mutex:
                        data_queue.queue.clear()

                    hw.set_led("IDLE")
                    stream.start()
        except queue.Empty:
            continue