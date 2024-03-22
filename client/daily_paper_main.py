from arxive_client import arXiv
from client.config_reader import ConfigReader
from client.s3_client import S3Client


if __name__ == "__main__":
    config_reader: ConfigReader = ConfigReader("client/config.ini")
    minio_client: S3Client = S3Client(
        config_reader.get_value("OSS", "endpoint"),
        config_reader.get_value("OSS", "access_key"),
        config_reader.get_value("OSS", "secret_key"),
    )

    # cs, physics, math, econ
    category = "cs.AI"
    # feed_url = f"http://rss.arxiv.org/rss/{category}"
    feed_url = f"http://export.arxiv.org/rss/{category}"
    minio_bucket = "city-brain-vendor"
    minio_path = "tq_deploy/tj_deploy_owner_yejibing/pdf-parser/arxiv/"
    arxiv = arXiv(
        feed_url,
        category,
        minio_client,
        minio_bucket,
        minio_path,
    )
    arxiv.process()
