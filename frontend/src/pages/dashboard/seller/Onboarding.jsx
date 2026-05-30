import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../../context/AuthContext';
import DashboardLayout from '../../../components/DashboardLayout';
import { Loader2, Sparkles, CheckCircle2 } from 'lucide-react';
import { useToast } from '../../../hooks/use-toast';

const Onboarding = () => {
  const { toast } = useToast();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const [interested, onboarding, active] = await Promise.all([
        axios.get(`${API}/seller-leads?stage=interested&limit=50`, { withCredentials: true }),
        axios.get(`${API}/seller-leads?stage=onboarding&limit=50`, { withCredentials: true }),
        axios.get(`${API}/seller-leads?stage=active&limit=50`, { withCredentials: true }),
      ]);
      setLeads([...(interested.data?.leads || []),
                ...(onboarding.data?.leads || []),
                ...(active.data?.leads || [])]);
    } catch (e) {
      toast({ title: 'Load failed', variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const onboard = async (lead) => {
    setBusy((b) => ({ ...b, [lead.id]: true }));
    try {
      const r = await axios.post(`${API}/seller-onboarding/start`,
        { lead_id: lead.id }, { withCredentials: true });
      toast({ title: r.data.reused ? 'Already onboarded' : 'Onboarding complete',
              description: `${(r.data.steps || []).length} steps · status=${r.data.status}` });
      load();
    } catch (e) {
      toast({ title: 'Onboarding failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setBusy((b) => ({ ...b, [lead.id]: false })); }
  };

  return (
    <DashboardLayout
      title="Seller OS · Onboarding"
      subtitle="Promote interested sellers into active marketplace members in under 10 minutes."
    >
      <div className="space-y-3" data-testid="seller-onboarding-page">
        {loading && <div className="flex items-center gap-2 text-zinc-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>}
        {!loading && leads.length === 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-10 text-center text-[13px] text-zinc-500">
            No interested or onboarding sellers yet. Once a thread converts (event=replied), it surfaces here.
          </div>
        )}
        {leads.map((lead) => (
          <div key={lead.id} className="rounded-2xl border border-white/5 bg-white/[0.03] p-4 flex items-center gap-3"
               data-testid={`onboard-row-${lead.id}`}>
            <div className="flex-1 min-w-0">
              <div className="text-[14px] font-semibold text-white truncate">{lead.business_name}</div>
              <div className="text-[11.5px] text-zinc-500 mt-0.5 flex items-center gap-2">
                <span className="capitalize">{lead.stage}</span>
                {lead.niche && <><span>·</span><span>{lead.niche}</span></>}
                {lead.seller_score != null && <><span>·</span><span>score {lead.seller_score}</span></>}
              </div>
            </div>
            {lead.stage === 'active' ? (
              <span className="text-[11.5px] font-semibold text-emerald-300 flex items-center gap-1">
                <CheckCircle2 size={12} /> Onboarded
              </span>
            ) : (
              <button onClick={() => onboard(lead)} disabled={busy[lead.id]}
                      data-testid={`onboard-start-${lead.id}`}
                      className="text-[12px] font-semibold px-3 py-1.5 rounded-md bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition flex items-center gap-1.5 disabled:opacity-50">
                {busy[lead.id] ? <Loader2 className="animate-spin" size={12} /> : <Sparkles size={12} />}
                Onboard now
              </button>
            )}
          </div>
        ))}
      </div>
    </DashboardLayout>
  );
};

export default Onboarding;
