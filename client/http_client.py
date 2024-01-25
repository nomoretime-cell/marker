import queue
import threading
import requests
import json
import uuid

data_index: int = 0
file_index: int = 0
concurrency_lock = threading.Lock()


class HttpClient:
    def __init__(self, server_url: str):
        self.server_url: str = server_url

    def start_send_thread(
        self: str, message_queue: queue.Queue, save_presigned_url: str
    ):
        while True:
            message = message_queue.get()
            if message is None:
                break
            message_body = {
                "requestId": str(uuid.uuid4()),
                "inFileUrl": message.inFileUrl,
                "outFileUrl": message.outFileUrl,
                # "maxPages": 100,
                # "parallelFactor": 1,
                # "isDebug": True,
            }
            if save_presigned_url == "True":
                self.append_to_jsonl(message)
            else:
                self.send_post_request(message_body)

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
            if data_index % (10000 * 20) == 0:
                file_index = file_index + 1
            with open(file_path, "a", encoding="utf-8") as file:
                json_line = json.dumps(jsonl, ensure_ascii=False)
                file.write(json_line + "\n")

    def send_post_request(self, message_body: dict):
        try:
            response = requests.post(
                self.server_url,
                data=json.dumps(message_body, default=lambda o: o.__dict__),
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                print(
                    f"Successful POST request, thread id: {threading.current_thread().ident} Response: {response.json()}"
                )
            else:
                print(f"Failed POST request. Status code: {response.status_code}")

        except Exception as e:
            print(f"Error sending POST request: {e}")
