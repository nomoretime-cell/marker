class MessageBody:
    def __init__(self, get_presigned_url: str, generate_presigned_url: str = ""):
        self.get_presigned_url: str = get_presigned_url
        self.generate_presigned_url: str = generate_presigned_url
def serialize_message_body(obj):
    return {'generate_presigned_url': obj.generate_presigned_url, 'get_presigned_url': obj.get_presigned_url}