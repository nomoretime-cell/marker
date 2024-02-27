import json
import queue
from datetime import timedelta
from typing import Generator
from minio import Minio
from minio.error import MinioException
from client.structure import MessageBody


class S3Client:
    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, secure: bool = False
    ) -> None:
        if not endpoint or not access_key or not secret_key:
            raise ValueError("'endpoint' or 'access key' or 'secret key' is Empty")
        self.minio_client: Minio = Minio(
            endpoint,
            access_key,
            secret_key,
            secure=secure,
        )
        self.file_cache: list[str] = []

    def replace_extension(self, filename, new_extension=".md"):
        dot_index = filename.rfind(".")
        if dot_index != -1:
            return filename[:dot_index] + new_extension
        else:
            return filename + new_extension

    def get_presigned_url(
        self, bucket_name: str, object_name: str, expiration: int
    ) -> str:
        try:
            presigned_url = self.minio_client.presigned_get_object(
                bucket_name, object_name, expires=timedelta(seconds=expiration)
            )
            return presigned_url
        except MinioException as e:
            print(f"Error getting presigned URL: {e}")
            return None

    def generate_presigned_url(
        self, bucket_name: str, object_name: str, expiration: int
    ) -> str:
        try:
            presigned_url = self.minio_client.presigned_put_object(
                bucket_name, object_name, expires=timedelta(seconds=expiration)
            )
            return presigned_url
        except MinioException as e:
            print(f"Error generating presigned URL: {e}")
            return None

    def list_objects_path(
        self,
        bucket_name: str,
        folder_path: str,
        file_type: list[str],
        limit: int = None,
    ) -> Generator[str, None, None]:
        objects: list = self.minio_client.list_objects(
            bucket_name, prefix=folder_path, recursive=True
        )
        obj_count = 0
        for obj in objects:
            obj_name: str = obj.object_name

            contained = False
            for type in file_type:
                if obj_name.endswith(type):
                    contained = True
                    break
            if not contained:
                continue
            obj_count += 1
            yield obj_name
            if limit is not None and obj_count >= limit:
                break

    def prepare_msg(
        self,
        queue: queue.Queue[MessageBody],
        bucket_name: str,
        object_path: str,
        out_folder_path: str,
        signed: bool = False,
        expiration: int = 3600,
    ):
        file_original_name = object_path.rsplit("/", 1)[-1]
        out_object_path = out_folder_path + self.replace_extension(file_original_name)

        if not signed:
            queue.put(MessageBody(file_original_name, object_path, out_object_path))
        else:
            queue.put(
                MessageBody(
                    file_original_name,
                    self.get_presigned_url(bucket_name, object_path, expiration),
                    self.generate_presigned_url(
                        bucket_name, out_object_path, expiration
                    ),
                )
            )

    def prepare_object(
        self,
        queue: queue.Queue[MessageBody],
        bucket_name: str,
        folder_path: str,
        out_folder_path: str,
        file_type: list[str],
        limit: int = None,
        signed: bool = False,
        expiration: int = 3600,
    ) -> None:
        for object_path in self.list_objects_path(
            bucket_name, folder_path, file_type, limit
        ):
            self.prepare_msg(
                queue, bucket_name, object_path, out_folder_path, signed, expiration
            )

    def filter_object(
        self,
        queue: queue.Queue[MessageBody],
        bucket_name: str,
        folder_path: str,
        out_folder_path: str,
        file_type: list[str],
        limit: int = None,
        filter_key: dict = None,
        signed: bool = False,
        expiration: int = 3600,
    ) -> None:
        for object_path in self.list_objects_path(
            bucket_name, folder_path, file_type, limit
        ):
            object_list: list = []
            # get file list from folder
            file = self.minio_client.get_object(bucket_name, object_path)
            try:
                for line in file.stream(512 * 1024 * 1024):
                    for json_object in line.decode("utf-8").splitlines():
                        json_object = json.loads(json_object)
                        filter_flag = False
                        for key, value in filter_key.items():
                            if json_object[key] != value:
                                filter_flag = True
                                break
                        if filter_flag:
                            continue
                        if json_object["path"].rsplit("/", 1)[-1] not in self.file_cache:
                            self.file_cache.append(json_object["path"].rsplit("/", 1)[-1])
                            object_list.append(json_object)
            except Exception as e:
                print(f"Error loading json: {e}")
            finally:
                file.close()
                file.release_conn()
            for obj in object_list:
                self.prepare_msg(
                    queue, obj["bucket"], obj["path"], out_folder_path, signed, expiration
                )
