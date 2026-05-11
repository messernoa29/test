import { AuthGate } from '@/components/shell/AuthGate'
import { Sidebar } from '@/components/shell/Sidebar'
import { StorageBanner } from '@/components/shell/StorageBanner'
import { Topbar } from '@/components/shell/Topbar'

export default function ShellLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <div className="min-h-screen">
        <Sidebar />
        <div className="pl-[240px] transition-[padding] duration-200">
          <Topbar />
          <StorageBanner />
          <main>{children}</main>
        </div>
      </div>
    </AuthGate>
  )
}
