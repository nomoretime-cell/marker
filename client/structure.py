class MessageBody:
    def __init__(self, inFileUrl: str, outFileUrl: str = ""):
        self.inFileUrl: str = inFileUrl
        self.outFileUrl: str = outFileUrl


def serialize_message_body(obj):
    return {"inFileUrl": obj.inFileUrl, "outFileUrl": obj.outFileUrl}
