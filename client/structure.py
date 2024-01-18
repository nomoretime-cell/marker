class MessageBody:
    def __init__(self, file_original_name: str, inFileUrl: str, outFileUrl: str = ""):
        self.file_original_name = file_original_name
        self.inFileUrl: str = inFileUrl
        self.outFileUrl: str = outFileUrl


def serialize_message_body(obj):
    return {"inFileUrl": obj.inFileUrl, "outFileUrl": obj.outFileUrl}
