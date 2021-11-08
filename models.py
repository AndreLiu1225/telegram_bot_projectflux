from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy import create_engine
from sqlalchemy.orm import registry
import settings as bs


mapper_registry = registry()
Base = mapper_registry.generate_base()
engine = create_engine(bs.DATABASE_URL, future=True)


class ExceptUser(Base):
    __tablename__ = 'except_user'

    id = Column(Integer, primary_key=True)
    uid = Column(String)



class Message(Base):
    __tablename__ = 'message'

    id = Column(Integer, primary_key=True)
    msgid = Column(String)
    sender = Column(String)
    sender_name = Column(String)
    type = Column(String)  # text/photo/video/animatino
    text = Column(String)
    media = Column(String)
    sent = Column(DateTime)
    replied = Column(Boolean, default=False)

    def __repr__(self):
        return f"Message(id={self.id!r}, msgid={self.msgid}, sender={self.sender!r}, sender_name={self.sender!r}, type={self.type!r}, text={self.text!r}, media={self.media!r}, sent={self.sent!r}, replied={self.replied!r})"


Base.metadata.create_all(engine)
