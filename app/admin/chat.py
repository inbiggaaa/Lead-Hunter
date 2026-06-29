"""Live chat: WebSocket-based support chat with users."""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, update, desc

from app.db.models import SupportMessage, User
from app.db.session import async_session_factory
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Active WebSocket connections: {admin_ws: set()}
active_connections: set[WebSocket] = set()


# ── REST: list user dialogs ──

@router.get("/chat/dialogs")
async def list_dialogs():
    """Return list of users with recent messages and unread count."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(
                SupportMessage.user_id,
                User.username,
                User.telegram_id,
                func.max(SupportMessage.created_at).label("last_msg"),
                func.count(SupportMessage.id).label("total"),
                func.sum(SupportMessage.is_read == False).label("unread"),
            )
            .join(User, SupportMessage.user_id == User.id)
            .group_by(SupportMessage.user_id, User.username, User.telegram_id)
            .order_by(desc("last_msg"))
            .limit(50)
        )
        rows = result.all()

    dialogs = []
    for row in rows:
        dialogs.append({
            "user_id": row.user_id,
            "username": row.username or f"id{row.telegram_id}",
            "telegram_id": row.telegram_id,
            "last_msg": row.last_msg.isoformat() if row.last_msg else None,
            "total": row.total,
            "unread": int(row.unread or 0),
        })
    return {"dialogs": dialogs}


# ── REST: get chat history ──

@router.get("/chat/history/{user_id}")
async def get_history(user_id: int):
    """Return message history for a specific user."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(SupportMessage)
            .where(SupportMessage.user_id == user_id)
            .order_by(SupportMessage.created_at)
            .limit(200)
        )
        messages = result.scalars().all()

        # Mark as read
        await session.execute(
            update(SupportMessage)
            .where(SupportMessage.user_id == user_id, SupportMessage.is_read == False)
            .values(is_read=True)
        )
        await session.commit()

    history = []
    for msg in messages:
        history.append({
            "id": msg.id,
            "direction": msg.direction,
            "text": msg.text,
            "created_at": msg.created_at.isoformat(),
        })
    return {"messages": history}


# ── WebSocket ──

@router.websocket("/chat/ws")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    active_connections.add(ws)

    try:
        while True:
            data = await ws.receive_json()
            action = data.get("action")

            if action == "send":
                user_id = data["user_id"]
                text = data["text"]
                telegram_id = data["telegram_id"]

                # Save outgoing message
                async with async_session_factory() as session:
                    msg = SupportMessage(
                        user_id=user_id,
                        direction="outgoing",
                        text=text,
                        is_read=True,
                    )
                    session.add(msg)
                    await session.commit()

                # Send via Bot API
                from aiogram import Bot
                bot = Bot(token=settings.bot_token)
                try:
                    await bot.send_message(telegram_id, f"💬 Поддержка:\n\n{text}")
                except Exception:
                    logger.exception("Failed to send support reply to %d", telegram_id)
                finally:
                    await bot.session.close()

                # Notify admin
                await ws.send_json({"type": "sent", "ok": True})

            elif action == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        active_connections.discard(ws)


# ── HTML page ──

@router.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return CHAT_HTML


CHAT_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LeadHunter — Live Chat</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,sans-serif;display:flex;height:100vh;background:#f5f5f5}
.sidebar{width:300px;background:#fff;border-right:1px solid #e0e0e0;overflow-y:auto}
.sidebar h2{padding:16px;border-bottom:1px solid #e0e0e0;font-size:18px}
.dialog-item{padding:12px 16px;border-bottom:1px solid #f0f0f0;cursor:pointer;display:flex;justify-content:space-between;align-items:center}
.dialog-item:hover{background:#f9f9f9}
.dialog-item.active{background:#e3f2fd}
.dialog-item .name{font-weight:500}
.dialog-item .meta{font-size:12px;color:#999}
.dialog-item .badge{background:#f44336;color:#fff;border-radius:10px;padding:2px 8px;font-size:11px}
.chat-area{flex:1;display:flex;flex-direction:column}
.chat-header{padding:16px;background:#fff;border-bottom:1px solid #e0e0e0;font-weight:600}
.messages{flex:1;padding:16px;overflow-y:auto;display:flex;flex-direction:column;gap:8px}
.msg{max-width:70%;padding:10px 14px;border-radius:12px;line-height:1.4;word-wrap:break-word}
.msg.incoming{background:#e3f2fd;align-self:flex-start}
.msg.outgoing{background:#c8e6c9;align-self:flex-end}
.msg .time{font-size:10px;color:#999;margin-top:4px}
.input-area{display:flex;padding:12px;background:#fff;border-top:1px solid #e0e0e0;gap:8px}
.input-area input{flex:1;padding:10px;border:1px solid #ddd;border-radius:8px;font-size:14px}
.input-area button{padding:10px 20px;background:#1976d2;color:#fff;border:none;border-radius:8px;cursor:pointer}
.input-area button:hover{background:#1565c0}
.empty{display:flex;align-items:center;justify-content:center;height:100%;color:#999;font-size:16px}
</style>
</head>
<body>
<div class="sidebar">
<h2>💬 Чаты</h2>
<div id="dialogs"></div>
</div>
<div class="chat-area">
<div class="chat-header" id="chatHeader">Выберите диалог</div>
<div class="messages" id="messages"><div class="empty">👈 Выберите пользователя слева</div></div>
<div class="input-area">
<input type="text" id="msgInput" placeholder="Сообщение..." disabled onkeydown="if(event.key==='Enter')sendMsg()">
<button id="sendBtn" disabled onclick="sendMsg()">▶️</button>
</div>
</div>

<script>
let ws, currentUser=null, dialogs=[];

async function init(){await loadDialogs();connectWS();}
async function loadDialogs(){
const r=await fetch('/chat/dialogs');const d=await r.json();
dialogs=d.dialogs||[];
const el=document.getElementById('dialogs');
el.innerHTML=dialogs.map(d=>`<div class="dialog-item" onclick="selectUser(${d.user_id},'${d.username}',${d.telegram_id})">
<div><div class="name">${d.username}</div><div class="meta">${d.total} сообщ.</div></div>
${d.unread?`<span class="badge">${d.unread}</span>`:''}</div>`).join('');
}
function connectWS(){
const proto=location.protocol==='https:'?'wss':'ws';
ws=new WebSocket(proto+'://'+location.host+'/chat/ws');
ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.type==='new_msg'&&currentUser&&d.user_id===currentUser.id)appendMsg(d);};
ws.onclose=()=>{setTimeout(connectWS,3000);};
}
async function selectUser(id,name,tgid){
currentUser={id,name,telegram_id:tgid};
document.getElementById('chatHeader').textContent='💬 '+name;
document.getElementById('msgInput').disabled=false;
document.getElementById('sendBtn').disabled=false;
document.querySelectorAll('.dialog-item').forEach(el=>el.classList.remove('active'));
event.target.closest('.dialog-item').classList.add('active');
const r=await fetch('/chat/history/'+id);const d=await r.json();
const el=document.getElementById('messages');
el.innerHTML=d.messages.map(m=>`<div class="msg ${m.direction}"><div>${escHtml(m.text)}</div><div class="time">${new Date(m.created_at).toLocaleTimeString()}</div></div>`).join('');
el.scrollTop=el.scrollHeight;
}
function sendMsg(){
const input=document.getElementById('msgInput');
const text=input.value.trim();
if(!text||!currentUser||!ws)return;
ws.send(JSON.stringify({action:'send',user_id:currentUser.id,text:text,telegram_id:currentUser.telegram_id}));
appendMsg({direction:'outgoing',text:text,created_at:new Date().toISOString()});
input.value='';
}
function appendMsg(m){
const el=document.getElementById('messages');
el.insertAdjacentHTML('beforeend',`<div class="msg ${m.direction}"><div>${escHtml(m.text)}</div><div class="time">${new Date(m.created_at).toLocaleTimeString()}</div></div>`);
el.scrollTop=el.scrollHeight;
}
function escHtml(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
init();
</script>
</body></html>"""
