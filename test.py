import json
import tinytuya

# === НАСТРОЙКА СЕТИ ===
# Убедись, что этот IP совпадает с актуальным адресом розетки в Smart Life
target_ip = '192.168.0.20' 
tinytuya.set_debug(True)
print("Шаг 1: Чтение файла конфигурации devices.json...")

try:
    with open('devices.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Автоматически определяем структуру (массив или словарь)
    devices = []
    if isinstance(data, list):
        devices = data
    elif isinstance(data, dict):
        devices = data.get('result', [data])

    # Ищем розетку по новому ID или по ключевому слову в имени
    socket_info = None
    for d in devices:
        if d.get('id') == 'bf92458fb773b88fcdl2vp' or 'Socket' in d.get('name', ''):
            socket_info = d
            break
            
    if not socket_info and devices:
        socket_info = devices[0]  # Если не нашли по ID, берем первое устройство
        
    if not socket_info:
        raise ValueError("В файле devices.json не найдено ни одного устройства.")

    # Извлекаем параметры
    dev_id = socket_info.get('id')
    dev_name = socket_info.get('name', 'Wi-Fi Socket')
    actual_key = socket_info.get('key')

    print(f"  [+] Найдено устройство: {dev_name}")
    print(f"  [+] ID устройства: {dev_id}")
    print(f"  [+] Считанный Local Key: {actual_key}")
    print(f"  [+] Длина ключа: {len(actual_key) if actual_key else 0} символов")

    if not actual_key or len(actual_key) != 16:
        print("  [⚠️] ВНИМАНИЕ: Длина ключа не равна 16 символам! Возможно, данные повреждены.")

except Exception as e:
    print(f"❌ Ошибка при чтении конфигурации: {e}")
    exit(1)


print("\n" + "="*50)
print(f"Шаг 2: Тестирование подключения к {target_ip}")
print("="*50 + "\n")

# Перебираем протоколы от новых к старым
for version in [3.4, 3.3, 3.5]:
    print(f"--- Тестируем версию протокола {version} (Класс OutletDevice) ---")
    
    # Инициализируем специализированный класс для розеток
    plug = tinytuya.OutletDevice(dev_id, target_ip, actual_key)
    plug.set_version(version)
    plug.set_socketTimeout(3)  # Таймаут ожидания ответа — 3 секунды
    
    try:
        # Запрашиваем статус устройства
        status = plug.status()
        
        if status and 'Error' not in status:
            print(f"✅ УСПЕХ на версии {version}!")
            print("Полный статус устройства:")
            print(json.dumps(status, indent=2, ensure_ascii=False))
            
            # Извлекаем состояние реле (обычно это DPS-индекс 1 или 20)
            dps_data = status.get('dps', {})
            print(f"\nТекущая карта DPS: {dps_data}")
            
            # Демонстрационное переключение (опционально)
            # Чтобы проверить контроль, раскомментируй строку ниже:
            # plug.turn_on() 
            
            break
        else:
            err_msg = status.get('Error', 'Неизвестная ошибка дешифрации')
            err_code = status.get('Err', '---')
            print(f"Ошибка на версии {version}: {err_msg} (Код: {err_code})")
            
    except Exception as e:
        print(f"Исключение на версии {version}: {e}")
        
    print("-" * 40)
