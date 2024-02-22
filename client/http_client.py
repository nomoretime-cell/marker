import queue
import threading
import requests
import json
import uuid

from marker.service.struct.analyze_struct import AnalyzeResponse
from urllib.parse import urlparse, unquote

data_index: int = 0
concurrency_lock = threading.Lock()


class HttpClient:
    def __init__(self, server_url: str, analyze_mode: bool):
        self.analyze_mode: bool = analyze_mode
        if self.analyze_mode:
            self.server_url: str = server_url + "/analyze"
        else:
            self.server_url: str = server_url + "/parser"

    def start_send_thread(self: str, message_queue: queue.Queue):
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
            self.send_post_request(message_body)

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
                if self.analyze_mode:
                    parsed_url = urlparse(message_body["inFileUrl"])
                    bucket = parsed_url.netloc.split(".")[0]
                    path = unquote(
                        parsed_url.path[1:]
                    )  # Remove the leading '/' and decode URL encoding
                    jsonl: str = AnalyzeResponse.from_dict(response.json()).to_jsonl(
                        {"bucket": bucket, "path": path}
                    )
                    self.append_to_jsonl(jsonl)
            else:
                print(f"Failed POST request. Status code: {response.status_code}")

        except Exception as e:
            print(f"Error sending POST request: {e}")

    def append_to_jsonl(self, jsonl: str):
        global data_index
        with concurrency_lock:
            file_path: str = "tags-doc.jsonl"
            jsonl = {"id": data_index, **jsonl}
            data_index = data_index + 1
            with open(file_path, "a", encoding="utf-8") as file:
                json_line = json.dumps(jsonl, ensure_ascii=False)
                file.write(json_line + "\n")
