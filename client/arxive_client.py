from datetime import datetime
from io import BytesIO
import feedparser
import requests
import json

from client.s3_client import S3Client


class arXiv:
    def __init__(
        self, feed_url, category, minio_client: S3Client, upload_bucket, upload_path
    ):
        self.feed = feedparser.parse(feed_url)
        self.category = category
        self.minio_client = minio_client
        self.upload_bucket = upload_bucket
        self.upload_path = upload_path

    def get_link(self, link, type):
        return link.replace("abs", type).rsplit("/", 1)[0] + "/"

    def get_file_name(self, arxiv_id, type):
        return f"{arxiv_id}." + type

    def download_pdf(self, url, filename):
        response = requests.get(url)
        if response.status_code == 200:
            with open(filename, "wb") as file:
                file.write(response.content)
            print(f"Downloaded '{filename}'.")
        else:
            print(f"Failed to download file from {url}.")

    def process(self):
        print(f"arXiv feed title - {self.feed.feed.title}\n")
        print(f"arXiv feed published time - {self.feed.feed.published}\n")
        date_obj = datetime.strptime(
            self.feed.feed.published, "%a, %d %b %Y %H:%M:%S %z"
        )
        formatted_date = date_obj.strftime("%Y%m%d")
        meta_data_list = ""
        for entry in self.feed.entries:
            arxiv_id = entry.id.split(":")[-1]
            meta_data = {
                "id": arxiv_id,
                "title": entry.title,
                "author": entry.author,
                "summary": entry.summary,
                "link": entry.link,
            }

            pdf_url = self.get_link(entry.link, "pdf")
            pdf_filename = self.get_file_name(arxiv_id, "pdf")
            pdf_url += arxiv_id
            html_url = self.get_link(entry.link, "html")
            html_filename = self.get_file_name(arxiv_id, "html")
            html_url += arxiv_id
            if pdf_url:
                self.minio_client.download_and_upload(
                    pdf_url,
                    self.upload_bucket,
                    self.upload_path
                    + f"{self.category}/"
                    + f"{formatted_date}/"
                    + pdf_filename,
                )
            if html_url:
                self.minio_client.download_and_upload(
                    html_url,
                    self.upload_bucket,
                    self.upload_path
                    + f"{self.category}/"
                    + f"{formatted_date}/"
                    + html_filename,
                )
            meta_data_list += json.dumps(meta_data) + "\n"

        meta_bytes = BytesIO(meta_data_list.encode("utf-8"))
        self.minio_client.upload_object_bytes(
            self.upload_bucket,
            self.upload_path
            + f"{self.category}/"
            + f"{formatted_date}/"
            + "meta_info.txt",
            meta_bytes,
            meta_bytes.getbuffer().nbytes,
        )
