import json
from typing import List
from client.config_reader import ConfigReader
from client.marker_client import HttpClient
from client.s3_client import S3Client
from client.structure import MessageBody, serialize_message_body


if __name__ == "__main__":
    config_reader: ConfigReader = ConfigReader(
        "/home/yejibing/code/marker/client/config.ini"
    )

    minio_client: S3Client = S3Client(
        config_reader.get_value("OSS", "endpoint"),
        config_reader.get_value("OSS", "access_key"),
        config_reader.get_value("OSS", "secret_key"),
    )

    messages: List[MessageBody] = minio_client.explore_bucket(
        config_reader.get_value("OSS", "bucket"),
        config_reader.get_value("OSS", "folder_path"),
        config_reader.get_value("OSS", "out_folder_path"),
        "pdf",
        3,
        True,
    )

    print(json.dumps(messages, default=serialize_message_body))

    http_client = HttpClient(config_reader.get_value("MARKER", "url"))
    for message in messages:
        message_body = {
            "inFileUrl": message.get_presigned_url,
            "outFileUrl": message.generate_presigned_url,
            # "maxPages": 100,
            # "parallelFactor": 1,
        }
        http_client.send_post_request(message_body)
