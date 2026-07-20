import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Send, Loader2 } from "lucide-react";

interface DialogItem {
  user_id: number;
  username: string;
  telegram_id: number;
  last_msg: string | null;
  total: number;
  unread: number;
}

interface MessageItem {
  id: number;
  direction: string;
  text: string;
  created_at: string;
}

export default function ChatPage() {
  const [selectedUser, setSelectedUser] = useState<DialogItem | null>(null);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: dialogsData, isLoading: dialogsLoading } = useQuery<{ dialogs: DialogItem[] }>({
    queryKey: ["chat-dialogs"],
    queryFn: () => api("/api/chat/dialogs"),
    refetchInterval: 10_000,
  });

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/api/chat/ws`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "new_msg" && selectedUser && data.user_id === selectedUser.user_id) {
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now(),
            direction: data.direction || "incoming",
            text: data.text,
            created_at: new Date().toISOString(),
          },
        ]);
        queryClient.invalidateQueries({ queryKey: ["chat-dialogs"] });
      }
    };

    ws.onclose = () => {
      setTimeout(() => {
        if (wsRef.current?.readyState !== WebSocket.OPEN) {
          // Reconnect handled by outer scope
        }
      }, 3000);
    };

    return () => { ws.close(); };
  }, [selectedUser, queryClient]);

  const selectUser = async (dialog: DialogItem) => {
    setSelectedUser(dialog);
    try {
      const data = await api<{ messages: MessageItem[] }>(`/api/chat/history/${dialog.user_id}`);
      setMessages(data.messages);
    } catch {
      setMessages([]);
    }
  };

  const sendMessage = () => {
    const text = message.trim();
    if (!text || !selectedUser || !wsRef.current) return;

    wsRef.current.send(
      JSON.stringify({
        action: "send",
        user_id: selectedUser.user_id,
        text,
      })
    );
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now(),
        direction: "outgoing",
        text,
        created_at: new Date().toISOString(),
      },
    ]);
    setMessage("");
    queryClient.invalidateQueries({ queryKey: ["chat-dialogs"] });
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">💬 Live-чат</h1>

      <div className="flex h-[calc(100vh-12rem)] border rounded-lg overflow-hidden bg-card">
        {/* Sidebar */}
        <div className="w-80 border-r flex flex-col">
          <div className="p-4 border-b font-semibold">Диалоги</div>
          <ScrollArea className="flex-1">
            {dialogsLoading ? (
              <div className="flex items-center justify-center p-8">
                <Loader2 className="size-5 animate-spin text-muted-foreground" />
              </div>
            ) : dialogsData?.dialogs.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground text-center">Нет диалогов</p>
            ) : (
              dialogsData?.dialogs.map((d) => (
                <div
                  key={d.user_id}
                  onClick={() => selectUser(d)}
                  className={`flex items-center gap-3 px-4 py-3 border-b cursor-pointer hover:bg-accent transition-colors ${
                    selectedUser?.user_id === d.user_id ? "bg-accent" : ""
                  }`}
                >
                  <Avatar className="size-9 shrink-0">
                    <AvatarFallback className="text-xs">
                      {d.username.slice(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-sm truncate">{d.username}</span>
                      {d.unread > 0 && (
                        <Badge variant="destructive" className="text-xs px-1.5 scale-75">
                          {d.unread}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground truncate">
                      {d.total} сообщений
                    </p>
                  </div>
                </div>
              ))
            )}
          </ScrollArea>
        </div>

        {/* Chat area */}
        {selectedUser ? (
          <div className="flex-1 flex flex-col">
            <div className="px-4 py-3 border-b font-medium flex items-center gap-2">
              <Avatar className="size-8">
                <AvatarFallback className="text-xs">
                  {selectedUser.username.slice(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              {selectedUser.username}
            </div>
            <ScrollArea className="flex-1 p-4">
              <div className="space-y-3">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={`flex ${m.direction === "outgoing" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[70%] rounded-xl px-4 py-2 text-sm ${
                        m.direction === "outgoing"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted"
                      }`}
                    >
                      <p className="whitespace-pre-wrap break-words">{m.text}</p>
                      <p className="text-[10px] opacity-60 mt-1">
                        {new Date(m.created_at).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            </ScrollArea>
            <div className="flex gap-2 p-3 border-t">
              <Input
                placeholder="Сообщение..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendMessage()}
              />
              <Button size="icon" onClick={sendMessage}>
                <Send className="size-4" />
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            👈 Выберите диалог
          </div>
        )}
      </div>
    </div>
  );
}
