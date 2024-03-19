import threading
import time
import queue
from client.config_reader import ConfigReader
from client.http_client import HttpClient
from client.presigned_client import PresignedClient
from client.s3_client import S3Client

if __name__ == "__main__":
    config_reader: ConfigReader = ConfigReader("client/config.ini")

    start_time: float = time.time()
    # Queue
    message_queue: queue.Queue = queue.Queue(maxsize=1000)

    minio_client: S3Client = S3Client(
        config_reader.get_value("OSS", "endpoint"),
        config_reader.get_value("OSS", "access_key"),
        config_reader.get_value("OSS", "secret_key"),
    )
    # Producer
    if config_reader.get_value("Common", "filter_mode") != "True":
        producer_thread = threading.Thread(
            target=minio_client.prepare_object,
            args=(
                message_queue,
                config_reader.get_value("OSS", "bucket"),
                config_reader.get_value("OSS", "folder_path"),
                config_reader.get_value("OSS", "out_folder_path"),
                config_reader.get_value("OSS", "file_type").split(","),
                None
                if int(config_reader.get_value("Common", "limit")) <= 0
                else int(config_reader.get_value("Common", "limit")),
                True,
                3600 * 24 * 7 - 3600,
            ),
        )
    else:
        producer_thread = threading.Thread(
            target=minio_client.filter_object,
            args=(
                message_queue,
                config_reader.get_value("OSS", "bucket"),
                config_reader.get_value("OSS", "folder_path"),
                config_reader.get_value("OSS", "out_folder_path"),
                config_reader.get_value("OSS", "file_type").split(","),
                None
                if int(config_reader.get_value("Common", "limit")) <= 0
                else int(config_reader.get_value("Common", "limit")),
                True,
                3600 * 24 * 7 - 3600,
                {
                    "fileType": config_reader.get_value("DocFilter", "fileType"),
                    "contentType": config_reader.get_value("DocFilter", "contentType"),
                    "language": config_reader.get_value("DocFilter", "language"),
                    "columnNum": int(config_reader.get_value("DocFilter", "columnNum")),
                },
            ),
        )

    # Consumer
    if config_reader.get_value("Common", "presigned_mode") == "True":
        client = PresignedClient(
            int(config_reader.get_value("PresignedClient", "split_size"))
        )
    else:
        client = HttpClient(
            config_reader.get_value("HttpClient", "url"),
            True
            if config_reader.get_value("HttpClient", "analyze_mode") == "True"
            else False,
        )

    num_consumers = int(config_reader.get_value("Common", "concurrency"))
    consumer_threads = [
        threading.Thread(
            target=client.start_send_thread,
            args=(message_queue,),
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
