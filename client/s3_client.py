import queue
from datetime import timedelta
from typing import Generator, List
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

    def list_objects_path(
        self, bucket_name: str, folder_path: str, file_type: str, limit: int = None
    ) -> Generator[str, None, None]:
        objects: list = self.minio_client.list_objects(
            bucket_name, prefix=folder_path, recursive=True
        )
        obj_count = 0
        for obj in objects:
            obj_name: str = obj.object_name
            if not obj_name.endswith(file_type):
                continue
            obj_count += 1
            yield obj_name
            if limit is not None and obj_count >= limit:
                break

    def prepare_object(
        self,
        queue: queue.Queue[MessageBody],
        bucket_name: str,
        folder_path: str,
        out_folder_path: str,
        file_type: str,
        limit: int = None,
        signed: bool = False,
        expiration: int = 3600,
    ) -> None:
        for object_path in self.list_objects_path(
            bucket_name, folder_path, file_type, limit
        ):
            out_object_path = object_path.rsplit("/", 1)[-1]
            out_object_path = out_folder_path + out_object_path.replace(file_type, "md")

            if not signed:
                queue.put(MessageBody(object_path, out_object_path))
            else:
                queue.put(
                    MessageBody(
                        self.get_presigned_url(bucket_name, object_path, expiration),
                        self.generate_presigned_url(
                            bucket_name, out_object_path, expiration
                        ),
                    )
                )

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
