"""Dashboard + Live Chat — standalone FastAPI app on port 8002."""

import json
import logging
import uvicorn
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, update, desc, case

from app.db.models import User, Subscription, SupportMessage
from app.db.session import async_session_factory
from app.config import settings

logger = logging.getLogger(__name__)

# ── Navigation bar shared across pages ──

NAV = """
<div style="background:#1976d2;padding:10px 24px;display:flex;gap:20px;font-size:14px">
<a href="/" style="color:#fff;text-decoration:none">📊 Дашборд</a>
<a href="/chat" style="color:#fff;text-decoration:none">💬 Чат</a>
<a href="http://localhost:8001/admin" style="color:#bbdefb;text-decoration:none">⚙️ Админка →</a>
</div>
"""

app = FastAPI(title="Dashboard")

# WebSocket connections
active_connections: set[WebSocket] = set()


# ═══════════════ DASHBOARD ═══════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    async with async_session_factory() as session:
        total = (await session.execute(select(func.count(User.id)))).scalar() or 0
        paid = (await session.execute(
            select(func.count(Subscription.id)).where(Subscription.payment_status == "paid")
        )).scalar() or 0
        plan_result = await session.execute(select(User.plan, func.count(User.id)).group_by(User.plan))
        plan_data = {plan: count for plan, count in plan_result.all()}

    pl = list(plan_data.keys())
    pv = list(plan_data.values())

    return NAV + f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Dashboard</title></head>
<body style="margin:0;font-family:-apple-system,sans-serif;background:#f5f5f5">
<div style="max-width:1100px;margin:0 auto;padding:24px">
<h1 style="color:#333;margin-bottom:24px">📊 Дашборд LeadHunter</h1>
<div style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap">
<div style="flex:1;min-width:140px;background:#4CAF50;color:#fff;border-radius:8px;padding:16px;text-align:center"><div style="font-size:14px;opacity:0.9">👥 Всего</div><div style="font-size:32px;font-weight:bold">{total}</div></div>
<div style="flex:1;min-width:140px;background:#FF9800;color:#fff;border-radius:8px;padding:16px;text-align:center"><div style="font-size:14px;opacity:0.9">💰 Оплат</div><div style="font-size:32px;font-weight:bold">{paid}</div></div>
</div>
<div style="background:#fff;border-radius:8px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.12);max-width:400px">
<h4>📊 Тарифы</h4><canvas id="planChart" height="200"></canvas></div>
<p style="margin-top:16px"><a href="/chat" style="color:#1976d2">💬 Live Chat →</a></p>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>new Chart(document.getElementById('planChart'),{{type:'doughnut',data:{{labels:{pl},datasets:[{{data:{pv},backgroundColor:['#607D8B','#4CAF50','#FF9800','#2196F3']}}]}},options:{{responsive:true}}}});</script>
</body></html>"""


# ═══════════════ CHAT ═══════════════

@app.get("/chat/dialogs")
async def chat_dialogs():
    async with async_session_factory() as session:
        result = await session.execute(
            select(
                SupportMessage.user_id,
                User.username,
                User.telegram_id,
                func.max(SupportMessage.created_at).label("last_msg"),
                func.count(SupportMessage.id).label("total"),
                func.sum(case((SupportMessage.is_read == False, 1), else_=0)).label("unread"),
            )
            .join(User, SupportMessage.user_id == User.id)
            .group_by(SupportMessage.user_id, User.username, User.telegram_id)
            .order_by(desc("last_msg"))
            .limit(50)
        )
        rows = result.all()

    dialogs = [{
        "user_id": r.user_id, "username": r.username or f"id{r.telegram_id}",
        "telegram_id": r.telegram_id,
        "last_msg": r.last_msg.isoformat() if r.last_msg else None,
        "total": r.total, "unread": int(r.unread or 0),
    } for r in rows]
    return {"dialogs": dialogs}


@app.get("/chat/history/{user_id}")
async def chat_history(user_id: int):
    async with async_session_factory() as session:
        result = await session.execute(
            select(SupportMessage).where(SupportMessage.user_id == user_id).order_by(SupportMessage.created_at).limit(200)
        )
        messages = result.scalars().all()
        await session.execute(
            update(SupportMessage).where(SupportMessage.user_id == user_id, SupportMessage.is_read == False).values(is_read=True)
        )
        await session.commit()

    return {"messages": [{
        "id": m.id, "direction": m.direction, "text": m.text,
        "created_at": m.created_at.isoformat(),
    } for m in messages]}


@app.websocket("/chat/ws")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    active_connections.add(ws)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("action") == "send":
                user_id = data["user_id"]
                text = data["text"]
                telegram_id = data["telegram_id"]

                async with async_session_factory() as session:
                    session.add(SupportMessage(user_id=user_id, direction="outgoing", text=text, is_read=True))
                    await session.commit()

                from aiogram import Bot
                bot = Bot(token=settings.bot_token)
                try:
                    await bot.send_message(telegram_id, f"💬 Поддержка:\n\n{text}")
                except Exception:
                    logger.exception("Failed to send to %d", telegram_id)
                finally:
                    await bot.session.close()

                await ws.send_json({"type": "sent", "ok": True})
            elif data.get("action") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        active_connections.discard(ws)


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return NAV + """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><title>Chat</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,sans-serif;display:flex;height:100vh;background:#f5f5f5}
.sidebar{width:300px;background:#fff;border-right:1px solid #e0e0e0;overflow-y:auto}
.sidebar h2{padding:16px;border-bottom:1px solid #e0e0e0;font-size:18px}
.dialog-item{padding:12px 16px;border-bottom:1px solid #f0f0f0;cursor:pointer;display:flex;justify-content:space-between;align-items:center}
.dialog-item:hover{background:#f9f9f9}.dialog-item.active{background:#e3f2fd}
.dialog-item .name{font-weight:500}.dialog-item .meta{font-size:12px;color:#999}
.dialog-item .badge{background:#f44336;color:#fff;border-radius:10px;padding:2px 8px;font-size:11px}
.chat-area{flex:1;display:flex;flex-direction:column}
.chat-header{padding:16px;background:#fff;border-bottom:1px solid #e0e0e0;font-weight:600}
.messages{flex:1;padding:16px;overflow-y:auto;display:flex;flex-direction:column;gap:8px}
.msg{max-width:70%;padding:10px 14px;border-radius:12px;line-height:1.4;word-wrap:break-word}
.msg.incoming{background:#e3f2fd;align-self:flex-start}.msg.outgoing{background:#c8e6c9;align-self:flex-end}
.msg .time{font-size:10px;color:#999;margin-top:4px}
.input-area{display:flex;padding:12px;background:#fff;border-top:1px solid #e0e0e0;gap:8px}
.input-area input{flex:1;padding:10px;border:1px solid #ddd;border-radius:8px;font-size:14px}
.input-area button{padding:10px 20px;background:#1976d2;color:#fff;border:none;border-radius:8px;cursor:pointer}
.empty{display:flex;align-items:center;justify-content:center;height:100%;color:#999;font-size:16px}
</style></head><body>
<div class="sidebar"><h2>💬 Чаты</h2><div id="dialogs"></div></div>
<div class="chat-area"><div class="chat-header" id="chatHeader">Выберите диалог</div>
<div class="messages" id="messages"><div class="empty">👈 Выберите пользователя</div></div>
<div class="input-area"><input id="msgInput" placeholder="Сообщение..." disabled onkeydown="if(event.key==='Enter')sendMsg()">
<button id="sendBtn" disabled onclick="sendMsg()">▶️</button></div></div>
<script>
let ws,currentUser=null;
async function init(){await loadDialogs();connectWS()}
async function loadDialogs(){const r=await fetch('/chat/dialogs');const d=await r.json();dialogs=d.dialogs;document.getElementById('dialogs').innerHTML=dialogs.map(d=>`<div class="dialog-item" onclick="selectUser(${d.user_id},'${d.username}',${d.telegram_id})"><div><div class="name">${d.username}</div><div class="meta">${d.total} msg</div></div>${d.unread?`<span class="badge">${d.unread}</span>`:''}</div>`).join('')}
function connectWS(){const p=location.protocol==='https:'?'wss':'ws';ws=new WebSocket(p+'://'+location.host+'/chat/ws');ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.type==='new_msg'&&currentUser&&d.user_id===currentUser.id)appendMsg(d)};ws.onclose=()=>setTimeout(connectWS,3000)}
async function selectUser(id,name,tgid){currentUser={id,name,telegram_id:tgid};document.getElementById('chatHeader').textContent='💬 '+name;document.getElementById('msgInput').disabled=false;document.getElementById('sendBtn').disabled=false;document.querySelectorAll('.dialog-item').forEach(e=>e.classList.remove('active'));event.target.closest('.dialog-item').classList.add('active');const r=await fetch('/chat/history/'+id);const d=await r.json();const el=document.getElementById('messages');el.innerHTML=d.messages.map(m=>`<div class="msg ${m.direction}"><div>${escHtml(m.text)}</div><div class="time">${new Date(m.created_at).toLocaleTimeString()}</div></div>`).join('');el.scrollTop=el.scrollHeight}
function sendMsg(){const i=document.getElementById('msgInput');const t=i.value.trim();if(!t||!currentUser||!ws)return;ws.send(JSON.stringify({action:'send',user_id:currentUser.id,text:t,telegram_id:currentUser.telegram_id}));appendMsg({direction:'outgoing',text:t,created_at:new Date().toISOString()});i.value=''}
function appendMsg(m){const e=document.getElementById('messages');e.insertAdjacentHTML('beforeend',`<div class="msg ${m.direction}"><div>${escHtml(m.text)}</div><div class="time">${new Date(m.created_at).toLocaleTimeString()}</div></div>`);e.scrollTop=e.scrollHeight}
function escHtml(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
init();
</script></body></html>"""


def main():
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")


if __name__ == "__main__":
    main()
