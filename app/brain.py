"""
Модуль логики ассистента Лера
"""
import datetime
import time
import threading
import re
import requests
import feedparser
import tinytuya
from num2words import num2words
from config import (
    API_WEATHER_KEY, CITY, NEWS_RSS_URL,
    TUYA_DEVICE_ID, TUYA_IP, TUYA_LOCAL_KEY, 
    TUYA_VERSION, TUYA_TIMEOUT, ASSISTANT_NAME
)


class LeraBrain:
    """Логика голосового ассистента"""
    
    def __init__(self, tts_queue):
        self.name = ASSISTANT_NAME
        self.tts_queue = tts_queue
        self.alarms = []
        self.timers = {}
        self.listening_mode = False
        self.plug = None
        
        self._init_tuya()

    def _init_tuya(self):
        """Инициализация Tuya устройства"""
        print("tuya init...")
        try:
            self.plug = tinytuya.OutletDevice(TUYA_DEVICE_ID, TUYA_IP, TUYA_LOCAL_KEY)
            self.plug.set_version(TUYA_VERSION)
            self.plug.set_socketTimeout(TUYA_TIMEOUT)
            print("Tuya ready")
        except Exception as e:
            print(f"error init tuya: {e}")
            self.plug = None

    @staticmethod
    def declension(n, one, two, five):
        """Склонение числительных"""
        n = abs(n) % 100
        if 11 <= n <= 19:
            return five
        n %= 10
        if n == 1:
            return one
        if 2 <= n <= 4:
            return two
        return five

    def get_time(self):
        """Получить текущее время в словесной форме"""
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
        """Получить погоду"""
        url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_WEATHER_KEY}&units=metric&lang=ru"
        try:
            res = requests.get(url, timeout=5).json()
            temp = int(res['main']['temp'])
            desc = res['weather'][0]['description']
            return f"В Новосибирске сейчас {temp} {self.declension(temp, 'градус', 'градуса', 'градусов')}, {desc}."
        except Exception:
            return "Не удалось узнать погоду."

    def get_news(self):
        """Получить новости"""
        try:
            feed = feedparser.parse(NEWS_RSS_URL)
            if not feed.entries:
                return "Новостей нет."
            titles = [e.title for e in feed.entries[:3]]
            news = "Последние новости. " + ". ".join(titles)
            return news.replace('"', '').replace("«", "").replace("»", "")
        except Exception:
            return "Не удалось загрузить новости."

    @staticmethod
    def words_to_numbers(text):
        """Преобразовать слова в числа"""
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
        """Запустить таймер"""
        if minutes in self.timers:
            self.timers[minutes].cancel()
        t = threading.Timer(minutes * 60, self._timer_end, [minutes])
        self.timers[minutes] = t
        t.start()
        return f"Таймер на {minutes} {self.declension(minutes, 'минуту', 'минуты', 'минут')} запущен."

    def _timer_end(self, minutes):
        """Обработка завершения таймера"""
        self.tts_queue.put(f"Таймер на {minutes} минут завершён!")
        self.timers.pop(minutes, None)

    def cancel_timer(self, text):
        """Отменить таймер"""
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
        """Установить будильник"""
        match = re.search(r'(\d{1,2}):?(\d{2})?', time_str)
        if match:
            h = int(match.group(1))
            m = int(match.group(2)) if match.group(2) else 0
            alarm_time = f"{h:02d}:{m:02d}"
            self.alarms.append(alarm_time)
            return f"Будильник установлен на {alarm_time}."
        return "Не поняла время будильника."

    def cancel_alarms(self):
        """Отменить все будильники"""
        count = len(self.alarms)
        self.alarms.clear()
        return f"Отменено {count} будильников." if count > 0 else "Будильников нет."

    def background_tasks_checker(self):
        """Фоновая проверка будильников"""
        while True:
            now_str = datetime.datetime.now().strftime("%H:%M")
            if now_str in self.alarms:
                self.tts_queue.put(f"Будильник на {now_str}!")
                self.alarms.remove(now_str)
            time.sleep(30)

    def handle(self, text):
        """Обработать текстовую команду"""
        text = text.lower().strip()

        if not self.listening_mode:
            if self.name in text:
                self.listening_mode = True
                return "Да, слушаю."
            return None

        self.listening_mode = False

        # Отмена будильника
        if "будильник" in text and any(w in text for w in ["выключи", "отмени", "убери", "стоп"]):
            return self.cancel_alarms()

        # Отмена таймера
        if "таймер" in text and any(w in text for w in ["выключи", "отмени", "убери", "стоп"]):
            return self.cancel_timer(text)

        # Погода
        if "погода" in text:
            return self.get_weather()

        # Новости
        if "новости" in text or "новость" in text:
            return self.get_news()

        # Время
        if "время" in text or "час" in text or "времени" in text:
            return self.get_time()

        # Таймер
        if "таймер" in text:
            nums = self.words_to_numbers(text)
            if nums:
                return self.start_timer(nums[0])
            return "На сколько минут поставить таймер?"

        # Будильник
        if "будильник" in text:
            nums = self.words_to_numbers(text)
            if nums:
                time_str = f"{nums[0]:02d}" + (f":{nums[1]:02d}" if len(nums) > 1 else ":00")
                return self.set_alarm(time_str)

        # Управление розеткой
        if any(w in text for w in ["свет", "ламп", "розетк"]):
            if not self.plug:
                return "Модуль управления розеткой не настроен."
            
            if "включи" in text:
                try:
                    data = self.plug.turn_on(nowait=False)
                    print(f"[Tuya Debug] Ответ розетки: {data}")
                    
                    if data and 'Error' in data:
                        return "Ошибка отправки команды на розетку."
                    return "свет включен"
                except Exception as e:
                    print(f"error tuya {e}")
                    return "нет связи с устройством"
                    
            if "выключи" in text:
                try:
                    data = self.plug.turn_off(nowait=False)
                    print(f"[Tuya Debug] Ответ розетки: {data}")
                    
                    if data and 'Error' in data:
                        return "Ошибка отправки команды на розетку."
                    return "Свет выключен"
                except Exception as e:
                    print(f"error tuya {e}")
                    return "нет связи с устройством"

        return "Не поняла команду."
