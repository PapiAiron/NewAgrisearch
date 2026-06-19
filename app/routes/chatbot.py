import os
import logging
import time
from datetime import datetime
from functools import wraps
from uuid import uuid4
from flask import Blueprint, request, jsonify, session, current_app
from groq import Groq
from app import db
from app.models.chat import ChatConversation, ChatMessage

chatbot_bp = Blueprint('chatbot', __name__)
logger = logging.getLogger(__name__)
_demo_rate_buckets = {}

SYSTEM_PROMPT = """You are AgriBot, an expert agricultural assistant for AgriSearch — a farm management system used in Victoria, Laguna, Philippines.

You ONLY answer questions related to:
- Crops: planting, growing, harvesting, irrigation, fertilization, pest/disease control
- Livestock: raising, feeding, health, common diseases, vaccinations, breeds
- Soil management, composting, and land preparation
- Philippine agriculture practices, seasons, and regulations
- Farm economics, yield optimization, market prices for crops/livestock
- Agricultural tools, equipment, and technology
- Organic farming, sustainable practices
- Victoria, Laguna local farming context when relevant

RULES:
1. If a question is NOT related to agriculture, farming, crops, or livestock — politely decline and redirect: "I'm AgriBot and I can only help with agriculture-related questions. Please ask me about crops, farming, or livestock!"
2. Always give practical, actionable advice.
3. Keep responses concise and easy to understand.
4. When relevant, mention Philippine context (PAGASA seasons, DA Philippines guidelines, local crop varieties).
5. Format responses clearly — use bullet points for lists, short paragraphs for explanations.
6. Never discuss politics, entertainment, coding, finance, or any non-agricultural topic.

You are friendly, knowledgeable, and passionate about helping Filipino farmers."""


def get_groq_client():
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        return None
    return Groq(api_key=api_key)


def _build_reply(user_message, context_messages):
    """Send prompt to Groq and return assistant text reply."""
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    messages.extend(context_messages)
    messages.append({'role': 'user', 'content': user_message})

    response = get_groq_client().chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=messages,
        max_tokens=600,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def _client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _check_demo_rate_limit():
    """Return (allowed, remaining, retry_after)."""
    max_msgs = current_app.config.get('CHATBOT_DEMO_MAX_MESSAGES_PER_WINDOW', 8)
    window = current_app.config.get('CHATBOT_DEMO_WINDOW_SECONDS', 900)
    now = int(time.time())

    demo_session_id = session.get('demo_chat_id')
    if not demo_session_id:
        demo_session_id = uuid4().hex
        session['demo_chat_id'] = demo_session_id

    key = f"{_client_ip()}::{demo_session_id}"
    hits = _demo_rate_buckets.get(key, [])
    hits = [ts for ts in hits if now - ts < window]

    if len(hits) >= max_msgs:
        retry_after = window - (now - min(hits))
        _demo_rate_buckets[key] = hits
        return False, 0, max(1, retry_after)

    hits.append(now)
    _demo_rate_buckets[key] = hits
    remaining = max_msgs - len(hits)
    return True, remaining, 0


def _sanitize_history(raw_history, max_items, max_chars):
    cleaned = []
    if not isinstance(raw_history, list):
        return cleaned

    for item in raw_history[-max_items:]:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        content = (item.get('content') or '').strip()
        if role not in ('user', 'assistant'):
            continue
        if not content:
            continue
        if len(content) > max_chars:
            content = content[:max_chars]
        cleaned.append({'role': role, 'content': content})
    return cleaned


def api_auth(f):
    """Decorator: return 401 JSON if not logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated


# ── List conversations ───────────────────────────────────────────
@chatbot_bp.route('/conversations', methods=['GET'])
@api_auth
def list_conversations():
    convs = (ChatConversation.query
             .filter_by(user_id=session['user_id'])
             .order_by(ChatConversation.updated_at.desc())
             .all())
    return jsonify({'conversations': [c.to_dict() for c in convs]})


# ── Create new conversation ──────────────────────────────────────
@chatbot_bp.route('/conversations', methods=['POST'])
@api_auth
def create_conversation():
    conv = ChatConversation(user_id=session['user_id'], title='New Chat')
    db.session.add(conv)
    db.session.commit()
    return jsonify(conv.to_dict()), 201


# ── Get conversation + messages ──────────────────────────────────
@chatbot_bp.route('/conversations/<int:conv_id>', methods=['GET'])
@api_auth
def get_conversation(conv_id):
    conv = ChatConversation.query.filter_by(
        id=conv_id, user_id=session['user_id']).first_or_404()
    messages = [m.to_dict() for m in conv.messages]
    data = conv.to_dict()
    data['messages'] = messages
    return jsonify(data)


# ── Send message & get reply ─────────────────────────────────────
@chatbot_bp.route('/conversations/<int:conv_id>/ask', methods=['POST'])
@api_auth
def ask(conv_id):
    conv = ChatConversation.query.filter_by(
        id=conv_id, user_id=session['user_id']).first_or_404()

    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()

    if not user_message:
        return jsonify({'error': 'Empty message'}), 400
    if len(user_message) > 1000:
        return jsonify({'error': 'Message too long (max 1000 characters)'}), 400

    client = get_groq_client()
    if not client:
        return jsonify({'error': 'Chatbot is not configured. Please set GROQ_API_KEY in .env'}), 503

    # Save user message
    user_msg = ChatMessage(conversation_id=conv_id, role='user', content=user_message)
    db.session.add(user_msg)
    db.session.flush()   # assigns id without full commit

    # Is this the first message? (count includes the flushed user_msg)
    total_msgs = ChatMessage.query.filter_by(conversation_id=conv_id).count()
    is_first = (total_msgs == 1)

    # Build context: last 12 messages before this one, in chronological order
    context = (ChatMessage.query
               .filter_by(conversation_id=conv_id)
               .filter(ChatMessage.id != user_msg.id)
               .order_by(ChatMessage.created_at.desc())
               .limit(12)
               .all())
    context = list(reversed(context))

    context_messages = []
    for m in context:
        if m.role in ('user', 'assistant'):
            context_messages.append({'role': m.role, 'content': m.content})

    try:
        reply = _build_reply(user_message, context_messages)
    except Exception as e:
        db.session.rollback()
        logger.error(f'[CHATBOT] Groq error: {e}')
        return jsonify({'error': 'Sorry, I could not process your request. Please try again.'}), 500

    # Save assistant reply
    db.session.add(ChatMessage(conversation_id=conv_id, role='assistant', content=reply))

    # Auto-title from first user message
    new_title = None
    if is_first:
        new_title = user_message[:50].strip()
        if len(user_message) > 50:
            new_title += '…'
        conv.title = new_title

    conv.updated_at = datetime.utcnow()
    db.session.commit()

    result = {'reply': reply}
    if new_title:
        result['title'] = conv.title
    return jsonify(result)


# ── Delete conversation ──────────────────────────────────────────
@chatbot_bp.route('/conversations/<int:conv_id>', methods=['DELETE'])
@api_auth
def delete_conversation(conv_id):
    conv = ChatConversation.query.filter_by(
        id=conv_id, user_id=session['user_id']).first_or_404()
    db.session.delete(conv)
    db.session.commit()
    return jsonify({'ok': True})


# ── Public demo ask endpoint (no auth, no DB persistence) ─────────────
@chatbot_bp.route('/demo/ask', methods=['POST'])
def demo_ask():
    if not current_app.config.get('CHATBOT_DEMO_ENABLED', True):
        return jsonify({'error': 'Demo chatbot is currently disabled.'}), 403

    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()
    max_chars = current_app.config.get('CHATBOT_DEMO_MAX_MESSAGE_CHARS', 600)
    max_history_items = current_app.config.get('CHATBOT_DEMO_MAX_HISTORY_ITEMS', 8)

    if not user_message:
        return jsonify({'error': 'Empty message'}), 400
    if len(user_message) > max_chars:
        return jsonify({'error': f'Message too long (max {max_chars} characters)'}), 400

    allowed, remaining, retry_after = _check_demo_rate_limit()
    if not allowed:
        return jsonify({
            'error': 'Demo limit reached. Please wait and try again.',
            'retry_after_seconds': retry_after
        }), 429

    client = get_groq_client()
    if not client:
        return jsonify({'error': 'Chatbot is not configured. Please set GROQ_API_KEY in .env'}), 503

    context_messages = _sanitize_history(
        data.get('history', []),
        max_items=max_history_items,
        max_chars=max_chars,
    )

    try:
        reply = _build_reply(user_message, context_messages)
    except Exception as e:
        logger.error(f'[CHATBOT_DEMO] Groq error: {e}')
        return jsonify({'error': 'Sorry, I could not process your request. Please try again.'}), 500

    return jsonify({
        'reply': reply,
        'remaining_messages': remaining
    })
