"""Dashboard — standalone FastAPI app on port 8002."""

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from app.db.models import User, Subscription
from app.db.session import async_session_factory


app = FastAPI(title="Dashboard")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    async with async_session_factory() as session:
        total = (await session.execute(select(func.count(User.id)))).scalar() or 0
        paid = (await session.execute(
            select(func.count(Subscription.id)).where(Subscription.payment_status == "paid")
        )).scalar() or 0
        plan_result = await session.execute(
            select(User.plan, func.count(User.id)).group_by(User.plan)
        )
        plan_data = {plan: count for plan, count in plan_result.all()}

    pl = list(plan_data.keys())
    pv = list(plan_data.values())

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>LeadHunter Dashboard</title></head>
<body style="margin:0;font-family:-apple-system,sans-serif;background:#f5f5f5">
<div style="max-width:1100px;margin:0 auto;padding:24px">
<h1 style="color:#333;margin-bottom:24px">📊 Дашборд LeadHunter</h1>
<div style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap">
<div style="flex:1;min-width:140px;background:#4CAF50;color:#fff;border-radius:8px;padding:16px;text-align:center">
<div style="font-size:14px;opacity:0.9">👥 Всего пользователей</div>
<div style="font-size:32px;font-weight:bold;margin-top:4px">{total}</div></div>
<div style="flex:1;min-width:140px;background:#FF9800;color:#fff;border-radius:8px;padding:16px;text-align:center">
<div style="font-size:14px;opacity:0.9">💰 Оплат</div>
<div style="font-size:32px;font-weight:bold;margin-top:4px">{paid}</div></div>
</div>
<div style="background:#fff;border-radius:8px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.12);max-width:400px">
<h4>📊 Распределение по тарифам</h4><canvas id="planChart" height="200"></canvas>
</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
new Chart(document.getElementById('planChart'),{{type:'doughnut',data:{{labels:{pl},datasets:[{{data:{pv},backgroundColor:['#607D8B','#4CAF50','#FF9800','#2196F3']}}]}},options:{{responsive:true}}}});
</script></body></html>"""


def main():
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")


if __name__ == "__main__":
    main()
