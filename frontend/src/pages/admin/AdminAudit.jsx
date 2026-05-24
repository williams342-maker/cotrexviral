import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Pause, Play, Shield, ShieldOff, Trash2, UserCog, Megaphone, Edit3, History } from 'lucide-react';

const ACTION_META = {
  suspend_user: { label: 'Suspended user', icon: Pause, color: 'bg-amber-50 text-amber-700 border-amber-100' },
  unsuspend_user: { label: 'Unsuspended user', icon: Play, color: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
  promote_admin: { label: 'Promoted to admin', icon: Shield, color: 'bg-violet-50 text-violet-700 border-violet-100' },
  demote_admin: { label: 'Demoted admin', icon: ShieldOff, color: 'bg-neutral-100 text-neutral-700 border-neutral-200' },
  delete_user: { label: 'Deleted user', icon: Trash2, color: 'bg-rose-50 text-rose-700 border-rose-100' },
  impersonate_user: { label: 'Impersonated user', icon: UserCog, color: 'bg-sky-50 text-sky-700 border-sky-100' },
  create_broadcast: { label: 'Created broadcast', icon: Megaphone, color: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
  update_broadcast: { label: 'Updated broadcast', icon: Edit3, color: 'bg-amber-50 text-amber-700 border-amber-100' },
  delete_broadcast: { label: 'Deleted broadcast', icon: Trash2, color: 'bg-rose-50 text-rose-700 border-rose-100' },
};

const AdminAudit = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API}/admin/audit-log`, { withCredentials: true })
      .then((r) => setLogs(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <DashboardLayout title="Audit Log" subtitle="Every admin action across CortexViral, in order of most recent.">
      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : logs.length === 0 ? (
        <div className="bg-white rounded-3xl p-10 border border-neutral-200/70 text-center">
          <History className="text-neutral-300 mx-auto mb-2" size={28} />
          <p className="text-neutral-700 font-medium">No admin actions yet</p>
        </div>
      ) : (
        <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden">
          {logs.map((l, i) => {
            const meta = ACTION_META[l.action] || { label: l.action, icon: History, color: 'bg-neutral-100 text-neutral-700 border-neutral-200' };
            const Icon = meta.icon;
            return (
              <div key={l.id} className={`flex items-start gap-4 px-5 py-4 ${i < logs.length - 1 ? 'border-b border-neutral-100' : ''}`}>
                <div className={`shrink-0 w-9 h-9 rounded-lg ${meta.color} border flex items-center justify-center`}>
                  <Icon size={15} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[14px] font-medium">
                    <span className="text-neutral-900">{l.admin_name}</span>
                    <span className="text-neutral-500"> {meta.label.toLowerCase()}</span>
                    {l.target_email && (
                      <>
                        <span className="text-neutral-500"> • </span>
                        <span className="text-neutral-800">{l.target_email}</span>
                      </>
                    )}
                  </div>
                  {l.details && Object.keys(l.details).length > 0 && (
                    <div className="text-[12.5px] text-neutral-500 mt-0.5 truncate">
                      {Object.entries(l.details).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ')}
                    </div>
                  )}
                </div>
                <span className="text-[12px] text-neutral-400 shrink-0 whitespace-nowrap">{new Date(l.created_at).toLocaleString()}</span>
              </div>
            );
          })}
        </div>
      )}
    </DashboardLayout>
  );
};

export default AdminAudit;
