from app import db
from datetime import datetime


class ChatConversation(db.Model):
    __tablename__ = 'chat_conversations'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    title      = db.Column(db.String(120), nullable=False, default='New Chat')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    messages = db.relationship(
        'ChatMessage', backref='conversation', lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='ChatMessage.created_at.asc()'
    )

    def to_dict(self):
        return {
            'id':         self.id,
            'title':      self.title,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer,
                                db.ForeignKey('chat_conversations.id', ondelete='CASCADE'),
                                nullable=False, index=True)
    role            = db.Column(db.String(10), nullable=False)   # 'user' or 'assistant'
    content         = db.Column(db.Text, nullable=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':         self.id,
            'role':       self.role,
            'content':    self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
