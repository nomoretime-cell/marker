import os
import uuid
from fastapi import APIRouter
from pydantic import BaseModel

import time

import requests

from marker.convert import convert_single_pdf
from marker.models import load_all_models
import json
from minio import Minio


router = APIRouter()
model_lst = load_all_models()

client = Minio(
    # "0.0.0.0:9000",
    "30.220.144.140:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
)
bucket_name = "jibing"


class PDFFile(BaseModel):
    inFileName: str
    outFileName: str
    maxPages: int
    parallelFactor: int
    isDebug: bool = False


@router.post("/parser/", tags=["pdf parser"])
async def post_parser(pdf_file: PDFFile):
    download_file(
        pdf_file.inFileName,
        pdf_file.inFileName,
    )

    start_time = time.time()
    end_time = time.time()
    execution_time = end_time - start_time
    print(
        f"Function '{load_all_models.__name__}' took {execution_time} seconds to execute."
    )

    start_time = time.time()
    full_text, out_meta = convert_single_pdf(
        pdf_file.inFileName,
        model_lst,
        max_pages=pdf_file.maxPages,
        parallel_factor=pdf_file.parallelFactor,
    )
    end_time = time.time()
    execution_time = end_time - start_time
    print(
        f"Function '{convert_single_pdf.__name__}' took {execution_time} seconds to execute."
    )

    with open(pdf_file.outFileName, "w+", encoding="utf-8") as f:
        f.write(full_text)

    out_meta_filename = pdf_file.outFileName.rsplit(".", 1)[0] + "_meta.json"
    with open(out_meta_filename, "w+") as f:
        f.write(json.dumps(out_meta, indent=4))

    upload_file(pdf_file.outFileName, pdf_file.outFileName)
    return {"code": "200", "message": "success"}


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


@router.post("/v2/parser/", tags=["pdf parser"])
async def post_v2_parser(pdf_file: PDFFile):
    uuid_str = str(uuid.uuid4())
    local_pdf_file: str = uuid_str + ".pdf"
    local_md_file: str = uuid_str + ".md"
    download_presigned_file(
        pdf_file.inFileName,
        local_pdf_file,
    )

    start_time = time.time()
    end_time = time.time()
    execution_time = end_time - start_time
    print(
        f"Function '{load_all_models.__name__}' took {execution_time} seconds to execute."
    )

    start_time = time.time()
    full_text, out_meta = convert_single_pdf(
        local_pdf_file,
        model_lst,
        max_pages=pdf_file.maxPages,
        parallel_factor=pdf_file.parallelFactor,
    )
    end_time = time.time()
    execution_time = end_time - start_time
    print(
        f"Function '{convert_single_pdf.__name__}' took {execution_time} seconds to execute."
    )

    with open(local_md_file, "w+", encoding="utf-8") as f:
        f.write(full_text)

    upload_presigned_file(pdf_file.outFileName, local_md_file)
    if not pdf_file.isDebug:
        delete_file(local_pdf_file)
        delete_file(local_md_file)
    return {"code": "200", "message": "success"}


def download_presigned_file(signed_url, local_file_path):
    try:
        response = requests.get(signed_url)

        if response.status_code == 200:
            # 将响应内容写入本地文件
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
            print(f"Successfully uploaded file using presigned URL.")
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
