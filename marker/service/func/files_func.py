import os
import requests
from minio import Minio

client = Minio(
    # "0.0.0.0:9000",
    "30.220.144.140:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
)
bucket_name = "jibing"


def download_file(source_file: str, destination_file: str):
    found = client.bucket_exists(bucket_name)
    if not found:
        client.make_bucket(bucket_name)
        print("Created bucket", bucket_name)
    else:
        print("Bucket", bucket_name, "already exists")

    client.fget_object(
        bucket_name,
        destination_file,
        source_file,
    )


def upload_file(source_file: str, destination_file: str):
    found = client.bucket_exists(bucket_name)
    if not found:
        client.make_bucket(bucket_name)
        print("Created bucket", bucket_name)
    else:
        print("Bucket", bucket_name, "already exists")

    client.fput_object(
        bucket_name,
        destination_file,
        source_file,
    )
    print(
        source_file,
        "successfully uploaded as object",
        destination_file,
        "to bucket",
        bucket_name,
    )


def download_presigned_file(signed_url, local_file_path):
    try:
        response = requests.get(signed_url)

        if response.status_code == 200:
            with open(local_file_path, "wb") as file:
                file.write(response.content)
            print(f"Successfully downloaded file to {local_file_path}")
        else:
            print(f"Failed to download file. Status code: {response.status_code}")

    except Exception as e:
        print(f"Error downloading file: {e}")


def upload_presigned_file(presigned_url, local_file_path):
    try:
        with open(local_file_path, "rb") as file:
            response = requests.put(presigned_url, data=file)

        if response.status_code == 200:
            print(f"Successfully uploaded file using presigned URL: {presigned_url}")
        else:
            print(
                f"Failed to upload file using presigned URL. Status code: {response.status_code}"
            )

    except Exception as e:
        print(f"Error uploading file using presigned URL: {e}")


def delete_file(file_path):
    try:
        os.remove(file_path)
        print(f"Successfully deleted file: {file_path}")
    except Exception as e:
        print(f"Error deleting file: {e}")
