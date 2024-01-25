import threading
import time
import queue
import uuid
from client.config_reader import ConfigReader
from client.http_client import HttpClient
from client.s3_client import S3Client

if __name__ == "__main__":
    config_reader: ConfigReader = ConfigReader("client/config.ini")

    start_time: float = time.time()
    # Queue
    message_queue: queue.Queue = queue.Queue(maxsize=1000)

    # Producer
    minio_client: S3Client = S3Client(
        config_reader.get_value("OSS", "endpoint"),
        config_reader.get_value("OSS", "access_key"),
        config_reader.get_value("OSS", "secret_key"),
    )
    producer_thread = threading.Thread(
        target=minio_client.prepare_object,
        args=(
            message_queue,
            config_reader.get_value("OSS", "bucket"),
            config_reader.get_value("OSS", "folder_path"),
            config_reader.get_value("OSS", "out_folder_path"),
            "pdf",
            # int(config_reader.get_value("MARKER", "limit")),
            None,
            True,
            3600 * 24 * 7 - 3600,
        ),
    )

    # Consumer
    http_client = HttpClient(config_reader.get_value("MARKER", "url"))
    num_consumers = int(config_reader.get_value("MARKER", "concurrency"))
    consumer_threads = [
        threading.Thread(
            target=http_client.start_send_thread,
            args=(
                message_queue,
                config_reader.get_value("MARKER", "save_presigned_url"),
            ),
        )
        for _ in range(num_consumers)
    ]
    producer_thread.start()
    for consumer_thread in consumer_threads:
        consumer_thread.start()

    # Wait for all data to be processed
    producer_thread.join()
    for _ in range(num_consumers):
        message_queue.put(None)
    # Wait for all consumers to finish
    for consumer_thread in consumer_threads:
        consumer_thread.join()

    execution_time: float = time.time() - start_time
    print(f"Process all data took {execution_time} seconds to execute.")
