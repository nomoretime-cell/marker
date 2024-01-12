from datetime import timedelta
from typing import Generator, List
from minio import Minio
from minio.error import MinioException

from client.structure import MessageBody


class S3Client:
    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, secure: bool = False
    ) -> None:
        self.minio_client: Minio = Minio(
            endpoint,
            access_key,
            secret_key,
            secure=secure,
        )

    def list_objects_name(
        self, bucket_name: str, prefix: str, suffix: str, limit: int = None
    ) -> Generator[str, None, None]:
        objects: list = self.minio_client.list_objects(
            bucket_name, prefix=prefix, recursive=True
        )
        obj_count = 0
        for obj in objects:
            obj_name: str = obj.object_name
            if not obj_name.endswith(suffix):
                continue
            obj_count += 1
            yield obj_name
            if limit is not None and obj_count >= limit:
                break

    def explore_bucket(
        self,
        bucket_name: str,
        folder_path: str,
        out_folder_path: str,
        suffix: str,
        limit: int = None,
        signed: bool = False,
        expiration: int = 3600,
    ) -> List[MessageBody]:
        messages: List[MessageBody] = []
        for minio_object in self.list_objects_name(
            bucket_name, folder_path, suffix, limit
        ):
            # print(f"Object Name: {minio_object}")
            if not signed:
                messages.append(MessageBody(minio_object))
            else:
                out_minio_object = minio_object.rsplit("/", 1)[-1]
                out_minio_object = out_folder_path + out_minio_object.replace(suffix, "md")
                messages.append(
                    MessageBody(
                        self.get_presigned_url(bucket_name, minio_object, expiration),
                        self.generate_presigned_url(
                            bucket_name, out_minio_object, expiration
                        ),
                    )
                )
        return messages

    def get_presigned_url(
        self, bucket_name: str, object_name: str, expiration: int = 3600
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
        self, bucket_name: str, object_name: str, expiration: int = 3600
    ) -> str:
        try:
            presigned_url = self.minio_client.presigned_put_object(
                bucket_name, object_name, expires=timedelta(seconds=expiration)
            )
            return presigned_url
        except MinioException as e:
            print(f"Error generating presigned URL: {e}")
            return None
