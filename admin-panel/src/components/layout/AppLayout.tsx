import { Outlet, NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
} from "@/components/ui/sidebar";
import { Badge } from "@/components/ui/badge";
import {
  LayoutDashboard,
  Users,
  Globe,
  Radio,
  MessageSquare,
  Send,
  Settings,
  LogOut,
  CircleOff,
  TriangleAlert,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";

const NAV_ITEMS = [
  { to: "/", icon: LayoutDashboard, label: "Дашборд" },
  { to: "/users", icon: Users, label: "Пользователи" },
  { to: "/categories", icon: Globe, label: "Категории" },
  { to: "/channels", icon: Radio, label: "Каналы" },
  { to: "/stop-words", icon: CircleOff, label: "Стоп-слова" },
  { to: "/unmatched", icon: TriangleAlert, label: "Несматченные" },
  { to: "/chat", icon: MessageSquare, label: "Чат" },
  { to: "/broadcast", icon: Send, label: "Рассылка" },
  { to: "/settings", icon: Settings, label: "Настройки" },
];

interface DialogItem {
  user_id: number;
  unread: number;
}

export default function AppLayout() {
  const { logout } = useAuth();

  const { data: dialogsData } = useQuery<{ dialogs: DialogItem[] }>({
    queryKey: ["chat-dialogs-sidebar"],
    queryFn: () => api("/api/chat/dialogs"),
    refetchInterval: 10_000,
  });

  const unreadTotal = dialogsData?.dialogs.reduce((sum, d) => sum + (d.unread || 0), 0) ?? 0;

  return (
    <SidebarProvider>
      <div className="flex min-h-screen w-full">
        <Sidebar>
          <SidebarHeader>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton size="lg">
                  <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                    <span className="text-sm font-bold">LH</span>
                  </div>
                  <span className="font-semibold">LeadHunter</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarHeader>
          <SidebarContent>
            <SidebarGroup>
              <SidebarGroupLabel>Навигация</SidebarGroupLabel>
              <SidebarMenu>
                {NAV_ITEMS.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton asChild>
                      <NavLink
                        to={item.to}
                        end={item.to === "/"}
                        className={({ isActive }) =>
                          isActive ? "bg-accent text-accent-foreground" : ""
                        }
                      >
                        <item.icon className="size-4" />
                        <span>{item.label}</span>
                        {item.to === "/chat" && unreadTotal > 0 && (
                          <Badge
                            variant="destructive"
                            className="ml-auto px-1.5 py-0 text-xs rounded-full"
                          >
                            {unreadTotal}
                          </Badge>
                        )}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroup>
          </SidebarContent>
          <SidebarFooter>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton onClick={logout}>
                  <LogOut className="size-4" />
                  <span>Выйти</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarFooter>
        </Sidebar>
        <main className="flex-1 overflow-auto">
          <div className="container mx-auto p-6 max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>
    </SidebarProvider>
  );
}
