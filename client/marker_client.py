import requests
import json

class HttpClient:
    def __init__(self, server_url):
        self.server_url = server_url

    def send_post_request(self, message_body):
        try:
            response = requests.post(
                self.server_url,
                data=json.dumps(message_body, default=lambda o: o.__dict__),
                headers={'Content-Type': 'application/json'}
            )

            if response.status_code == 200:
                print(f'Successful POST request. Response: {response.json()}')
            else:
                print(f'Failed POST request. Status code: {response.status_code}')

        except Exception as e:
            print(f'Error sending POST request: {e}')