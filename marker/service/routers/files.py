import uuid
import time
import json

from fastapi import APIRouter
from marker.convert import convert_single_pdf
from marker.models import load_all_models
from marker.service.func.files_func import (
    delete_file,
    download_file,
    download_presigned_file,
    upload_file,
    upload_presigned_file,
)


from marker.service.struct.files_struct import ParserRequest


router = APIRouter()
model_lst = load_all_models()


@router.post("/parser/", tags=["pdf parser"])
async def post_parser(parser_request: ParserRequest):
    download_file(
        parser_request.inFileUrl,
        parser_request.inFileUrl,
    )

    start_time = time.time()
    end_time = time.time()
    execution_time = end_time - start_time
    print(
        f"Function '{load_all_models.__name__}' took {execution_time} seconds to execute."
    )

    start_time = time.time()
    full_text, out_meta = convert_single_pdf(
        parser_request.inFileUrl,
        model_lst,
        max_pages=parser_request.maxPages,
        parallel_factor=parser_request.parallelFactor,
    )
    end_time = time.time()
    execution_time = end_time - start_time
    print(
        f"Function '{convert_single_pdf.__name__}' took {execution_time} seconds to execute."
    )

    with open(parser_request.outFileUrl, "w+", encoding="utf-8") as f:
        f.write(full_text)

    out_meta_filename = parser_request.outFileUrl.rsplit(".", 1)[0] + "_meta.json"
    with open(out_meta_filename, "w+") as f:
        f.write(json.dumps(out_meta, indent=4))

    upload_file(parser_request.outFileUrl, parser_request.outFileUrl)
    return {"code": "200", "message": "success"}


@router.post("/v1/parser/", tags=["file parser"])
async def post_v2_parser(parser_request: ParserRequest):
    uuid_str = str(uuid.uuid4())
    local_parser_request: str = uuid_str + "." + parser_request.fileType
    local_md_file: str = uuid_str + ".md"
    download_presigned_file(
        parser_request.inFileUrl,
        local_parser_request,
    )

    start_time = time.time()
    end_time = time.time()
    execution_time = end_time - start_time
    print(
        f"Function '{load_all_models.__name__}' took {execution_time} seconds to execute."
    )

    start_time = time.time()
    full_text, out_meta = convert_single_pdf(
        local_parser_request,
        model_lst,
        max_pages=parser_request.maxPages,
        parallel_factor=parser_request.parallelFactor,
    )
    end_time = time.time()
    execution_time = end_time - start_time
    print(
        f"Function '{convert_single_pdf.__name__}' took {execution_time} seconds to execute."
    )

    with open(local_md_file, "w+", encoding="utf-8") as f:
        f.write(full_text)

    upload_presigned_file(parser_request.outFileUrl, local_md_file)
    if not parser_request.isDebug:
        delete_file(local_parser_request)
        delete_file(local_md_file)
    return {"code": "200", "message": "success", "requestId": parser_request.requestId}
