import logging
import os
import requests
from minio import Minio

# DEBUG MODE
client = Minio(
    "30.220.144.140:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
)
bucket_name = "jibing"
# DEBUG MODE


def download_file(source_file: str, destination_file: str) -> None:
    found = client.bucket_exists(bucket_name)
    if not found:
        client.make_bucket(bucket_name)
        logging.info(f"Created bucket {bucket_name}")
    else:
        logging.info(f"Bucket {bucket_name} already exists")

    client.fget_object(
        bucket_name,
        destination_file,
        source_file,
    )


def upload_file(source_file: str, destination_file: str) -> None:
    found = client.bucket_exists(bucket_name)
    if not found:
        client.make_bucket(bucket_name)
        logging.info(f"Created bucket {bucket_name}")
    else:
        logging.info(f"Bucket {bucket_name} already exists")

    client.fput_object(
        bucket_name,
        destination_file,
        source_file,
    )
    logging.info(
        f"{source_file} successfully uploaded as object {destination_file} to bucket {bucket_name}"
    )


def download_presigned_file(presigned_get_url: str, local_file_path: str) -> None:
    try:
        response = requests.get(presigned_get_url)

        if response.status_code == 200:
            with open(local_file_path, "wb") as file:
                file.write(response.content)
            logging.info(f"Successfully downloaded file to {local_file_path}")
        else:
            logging.info(
                f"Failed to download file. Status code: {response.status_code}"
            )

    except Exception as e:
        logging.error(f"Error downloading file: {e}")


def upload_presigned_file(
    presigned_put_url: str, local_file_path: str, local_file_content: str = None
) -> None:
    try:
        if local_file_content is not None:
            response = requests.put(presigned_put_url, data=local_file_content)
        else:
            with open(local_file_path, "rb") as file:
                response = requests.put(presigned_put_url, data=file)

        if response.status_code == 200:
            logging.info(
                f"Successfully uploaded file using presigned URL: {presigned_put_url}"
            )
        else:
            logging.error(
                f"Failed to upload file using presigned URL. Status code: {response.status_code}"
            )

    except Exception as e:
        logging.error(f"Error uploading file using presigned URL: {e}")


def delete_file(file_path: str) -> None:
    try:
        os.remove(file_path)
        logging.info(f"Successfully deleted file: {file_path}")
    except Exception as e:
        logging.error(f"Error deleting file: {e}")
