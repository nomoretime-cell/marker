import queue
import threading
import json

data_index: int = 0
file_index: int = 0
concurrency_lock = threading.Lock()


class PresignedClient:
    def __init__(self, split_size: int):
        self.split_size = split_size

    def start_send_thread(self: str, message_queue: queue.Queue):
        while True:
            message = message_queue.get()
            if message is None:
                break
            self.append_to_jsonl(message)

    def append_to_jsonl(self, message):
        global data_index
        global file_index
        with concurrency_lock:
            file_path: str = f"presigned_url-{file_index}.jsonl"
            jsonl = {
                "id": data_index,
                "name": message.file_original_name,
                "url": message.inFileUrl,
            }
            data_index = data_index + 1
            if data_index % (self.split_size) == 0:
                file_index = file_index + 1
            with open(file_path, "a", encoding="utf-8") as file:
                json_line = json.dumps(jsonl, ensure_ascii=False)
                file.write(json_line + "\n")
