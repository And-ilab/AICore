import asyncio
import websockets
import json
import queue
import sys
import os
from pathlib import Path
import sounddevice as sd
from vosk import Model, KaldiRecognizer


def resolve_model_path():
    """Return the first configured or existing Vosk model path."""
    configured = os.environ.get("VOSK_MODEL_PATH")
    service_dir = Path(__file__).resolve().parent
    candidates = [
        Path(configured).expanduser() if configured else None,
        service_dir / "model" / "vosk-model-ru-0.22",
        service_dir.parents[2] / "recognizer" / "model" / "vosk-model-ru-0.22",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return str(candidate.resolve())
    return str(next(candidate for candidate in candidates if candidate is not None).resolve())


class RealtimeTranscriber:
    def __init__(self, model_path=None, samplerate=16000):
        model_path = model_path or resolve_model_path()
        if not os.path.exists(model_path):
            print(f"Модель не найдена по пути: {model_path}")
            sys.exit(1)

        print(f"Загрузка модели из {model_path}...")
        try:
            self.model = Model(model_path)
            print("Модель загружена успешно")
        except Exception as e:
            print(f"Ошибка загрузки модели: {e}")
            sys.exit(1)

        self.samplerate = samplerate
        self.q = queue.Queue()
        self.is_running = False
        self.clients = set()
        self.recognizer = None
        self.stream = None

    def audio_callback(self, indata, frames, _time, status):
        """Обратный вызов для записи аудио"""
        if status:
            print(f"Аудио статус: {status}", file=sys.stderr)
        if self.is_running:
            self.q.put(bytes(indata))

    async def send_to_clients(self, message_type, text):
        """Отправка транскрипции всем подключенным клиентам"""
        if not text or text.strip() == "":
            return

        message = json.dumps({
            "type": message_type,
            "text": text.strip()
        })

        disconnected_clients = set()

        for client in self.clients:
            try:
                await client.send(message)
            except Exception:
                disconnected_clients.add(client)
                print("Клиент отключен при отправке")

        # Удаляем отключенных клиентов
        for client in disconnected_clients:
            self.clients.remove(client)

    async def handle_client(self, websocket):
        """Обработка нового клиента"""
        self.clients.add(websocket)
        print(f"Новый клиент подключен. Всего клиентов: {len(self.clients)}")

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    print(f"Получена команда: {data}")

                    if data.get("type") == "start_transcription":
                        print("Получена команда на запуск транскрипции")
                        if not self.is_running:
                            self.is_running = True
                            # Запускаем транскрипцию в отдельном потоке
                            asyncio.create_task(self.start_transcription())
                            await websocket.send(json.dumps({"type": "status", "text": "Транскрипция запущена"}))

                    elif data.get("type") == "stop_transcription":
                        print("Получена команда на остановку транскрипции")
                        self.is_running = False
                        await websocket.send(json.dumps({"type": "status", "text": "Транскрипция остановлена"}))

                except json.JSONDecodeError as e:
                    print(f"Ошибка декодирования JSON: {e}")

        except websockets.exceptions.ConnectionClosed:
            print("Клиент отключен")
        finally:
            if websocket in self.clients:
                self.clients.remove(websocket)
            print(f"Клиент удален. Всего клиентов: {len(self.clients)}")

    async def start_transcription(self):
        """Запуск транскрипции в реальном времени"""
        print("Транскрипция начата... Говорите в микрофон")

        rec = KaldiRecognizer(self.model, self.samplerate)
        rec.SetWords(True)
        rec.SetPartialWords(True)

        try:
            with sd.RawInputStream(
                    samplerate=self.samplerate,
                    blocksize=8000,
                    dtype='int16',
                    channels=1,
                    callback=self.audio_callback
            ) as stream:
                self.stream = stream

                while self.is_running:
                    try:
                        # Получаем данные из очереди
                        data = self.q.get_nowait()

                        if rec.AcceptWaveform(data):
                            result = json.loads(rec.Result())
                            text = result.get("text", "").strip()
                            if text:
                                print(f"✅ ФИНАЛЬНО: {text}")
                                await self.send_to_clients("final", text)
                        else:
                            partial_result = json.loads(rec.PartialResult())
                            partial_text = partial_result.get("partial", "").strip()
                            if partial_text:
                                print(f"📝 Частично: {partial_text}")
                                await self.send_to_clients("partial", partial_text)

                    except queue.Empty:
                        # Нет новых аудио данных - небольшая пауза
                        await asyncio.sleep(0.01)
                        continue
                    except Exception as e:
                        print(f"Ошибка обработки: {e}")
                        continue

        except Exception as e:
            print(f"Ошибка при записи: {e}")
        finally:
            self.is_running = False
            self.stream = None
            print("Транскрипция остановлена")

    async def run_server(self):
        """Запуск WebSocket сервера"""
        async with websockets.serve(self.handle_client, "localhost", 8765):
            print("✅ Суфлер запущен и слушает на ws://localhost:8765")
            print("📞 Готов к распознаванию речи во время звонков")
            print("⏳ Ожидание подключения интерфейса...")

            # Периодическая проверка состояния
            while True:
                await asyncio.sleep(5)
                if self.clients:
                    print(f"Активных клиентов: {len(self.clients)}")


def main():
    """Основная функция"""
    transcriber = RealtimeTranscriber()

    try:
        asyncio.run(transcriber.run_server())
    except KeyboardInterrupt:
        print("\n\n🛑 Суфлер остановлен пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
