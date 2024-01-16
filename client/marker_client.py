import queue
import threading
import requests
import json
import uuid


class HttpClient:
    def __init__(self, server_url: str, message_queue: queue.Queue):
        self.server_url: str = server_url
        self.message_queue: queue.Queue = message_queue


    def start_send_thread(self):
        while True:
            message = self.message_queue.get()
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
                print(f"Successful POST request, thread id: {threading.current_thread().ident} Response: {response.json()}")
            else:
                print(f"Failed POST request. Status code: {response.status_code}")

        except Exception as e:
            print(f"Error sending POST request: {e}")
