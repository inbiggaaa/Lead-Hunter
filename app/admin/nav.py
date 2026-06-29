"""Navigation links view for SQLAdmin sidebar."""

from sqladmin import BaseView, expose
from fastapi.responses import RedirectResponse


class NavView(BaseView):
    name = "📊 Дашборд"
    icon = "fa-external-link"
    identity = "nav-dashboard"

    @expose("/go-dashboard", methods=["GET"])
    async def go_dashboard(self, request):
        return RedirectResponse(url="http://localhost:8002/")


class NavChatView(BaseView):
    name = "💬 Live-чат"
    icon = "fa-comments"
    identity = "nav-chat"

    @expose("/go-chat", methods=["GET"])
    async def go_chat(self, request):
        return RedirectResponse(url="http://localhost:8002/chat")
