import tinytuya
import json

# 1. Автоматически читаем ключ из оригинального файла визарда
try:
    with open('devices.json', 'r') as f:
        devices_list = json.load(f)
    
    # Берем первое устройство из списка
    dev = devices_list[0]
    dev_id = dev['id']
    actual_key = dev['key']
    
    print(f" Найдено в devices.json:")
    print(f"  Имя: {dev['name']}")
    print(f"  ID:  {dev_id}")
    print(f"  Ключ успешно загружен из кэша (длина {len(actual_key)} символов)\n")

except Exception as e:
    print(f"❌ Не удалось прочитать devices.json: {e}")
    exit()

# 2. Перебираем версии протокола с чистым ключом
target_ip = '192.168.0.20'

for version in [3.4, 3.3, 3.5]:
    print(f"--- Тестируем версию протокола {version} ---")
    
    # Инициализируем базовый класс устройства
    plug = tinytuya.Device(dev_id, target_ip, actual_key)
    plug.set_version(version)
    plug.set_socketTimeout(3)
    
    try:
        status = plug.status()
        if status and 'Error' not in status:
            print(f"✅ УСПЕХ на версии {version}!")
            print("Ответ розетки:", status)
            
            print("\nПробуем переключить реле для проверки...")
            payload = plug.generate_payload(tinytuya.CONTROL, {'1': True})
            print("Результат команды:", plug.send(payload))
            break
        else:
            print(f"Ошибка на версии {version}: {status.get('Error')} (Код: {status.get('Err')})")
    except Exception as e:
        print(f"Исключение на версии {version}: {e}")
    print("-" * 40)
