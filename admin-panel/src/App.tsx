import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "@/lib/auth";
import { Toaster } from "@/components/ui/sonner";
import AppLayout from "@/components/layout/AppLayout";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import UsersPage from "@/pages/UsersPage";
import CatalogPage from "@/pages/CatalogPage";
import ChannelsPage from "@/pages/ChannelsPage";
import ChatPage from "@/pages/ChatPage";
import BroadcastPage from "@/pages/BroadcastPage";
import SettingsPage from "@/pages/SettingsPage";
import StopWordsPage from "@/pages/StopWordsPage";
import UnmatchedPage from "@/pages/UnmatchedPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted-foreground">Загрузка...</p>
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<DashboardPage />} />
              <Route path="users" element={<UsersPage />} />
              <Route path="catalog" element={<CatalogPage />} />
              <Route path="channels" element={<ChannelsPage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="broadcast" element={<BroadcastPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="stop-words" element={<StopWordsPage />} />
              <Route path="unmatched" element={<UnmatchedPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster />
      </AuthProvider>
    </QueryClientProvider>
  );
}
