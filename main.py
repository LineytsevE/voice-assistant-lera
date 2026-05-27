"""
Главный модуль голосового ассистента Лера
"""
import queue
import threading
import sounddevice as sd
from config import SAMPLE_RATE, BLOCK_SIZE, AUDIO_CHANNELS, ASSISTANT_NAME
from tts import FastPiper, synth_and_say
from stt import SpeechRecognizer
from brain import LeraBrain


def main():
    """Главная функция ассистента"""
    # Инициализация очередей
    data_queue = queue.Queue()
    tts_queue = queue.Queue()
    
    # Инициализация модулей
    brain = LeraBrain(tts_queue)
    voice = FastPiper()
    recognizer = SpeechRecognizer()
    
    # Запуск фоновой проверки будильников
    threading.Thread(target=brain.background_tasks_checker, daemon=True).start()
    
    # Callback для аудио потока
    def callback(indata, frames, time_info, status):
        data_queue.put(bytes(indata))
    
    print(f"\n{ASSISTANT_NAME.capitalize()} запущена. Говорите '{ASSISTANT_NAME.capitalize()}' для активации.\n")
    
    # Главный цикл
    with sd.RawInputStream(
        samplerate=SAMPLE_RATE, 
        blocksize=BLOCK_SIZE, 
        dtype='int16', 
        channels=AUDIO_CHANNELS, 
        callback=callback
    ) as stream:
        while True:
            # 1. Проверяем фоновые сообщения (таймеры/будильники)
            try:
                bg_message = tts_queue.get_nowait()
                stream.stop()
                try:
                    hw.set_led("SPEAK")
                except:
                    pass
                
                synth_and_say(voice, bg_message)
                
                try:
                    hw.set_led("IDLE")
                except:
                    pass
                stream.start()
            except queue.Empty:
                pass

            # 2. Слушаем микрофон
            try:
                data = data_queue.get(timeout=0.1)
                result = recognizer.process_audio(data)
                
                if result:
                    print(f"Распознано: {result}")
                    try:
                        hw.set_led("LISTEN")
                    except:
                        pass
                    
                    response = brain.handle(result)
                    if response:
                        stream.stop()
                        try:
                            hw.set_led("SPEAK")
                        except:
                            pass
                        
                        synth_and_say(voice, response)
                        
                        try:
                            hw.set_led("IDLE")
                        except:
                            pass
                        stream.start()
            except queue.Empty:
                continue


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        voice.Close()
        print("\nЗавершение работы...")
    except Exception as e:
        print(f"Ошибка: {e}")
