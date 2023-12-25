from fastapi import APIRouter
from pydantic import BaseModel

import time

from marker.convert import convert_single_pdf
from marker.models import load_all_models
import json
from minio import Minio


router = APIRouter()
model_lst = load_all_models()

client = Minio(
    "0.0.0.0:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
)
bucket_name = "jibing"


class PDFFile(BaseModel):
    fname: str
    output: str
    max_pages: int
    parallel_factor: int


@router.post("/parser/", tags=["pdf parser"])
async def post_parser(pdf_file: PDFFile):
    download_file(
        pdf_file.fname,
        pdf_file.fname,
    )

    start_time = time.time()
    end_time = time.time()
    execution_time = end_time - start_time
    print(
        f"Function '{load_all_models.__name__}' took {execution_time} seconds to execute."
    )

    start_time = time.time()
    full_text, out_meta = convert_single_pdf(
        pdf_file.fname,
        model_lst,
        max_pages=pdf_file.max_pages,
        parallel_factor=pdf_file.parallel_factor,
    )
    end_time = time.time()
    execution_time = end_time - start_time
    print(
        f"Function '{convert_single_pdf.__name__}' took {execution_time} seconds to execute."
    )

    with open(pdf_file.output, "w+", encoding="utf-8") as f:
        f.write(full_text)

    out_meta_filename = pdf_file.output.rsplit(".", 1)[0] + "_meta.json"
    with open(out_meta_filename, "w+") as f:
        f.write(json.dumps(out_meta, indent=4))

    upload_file(pdf_file.output, pdf_file.output)
    return {"status": "ok"}


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
