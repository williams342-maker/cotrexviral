import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Inbox, Mail, Globe } from 'lucide-react';

const Leads = () => {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API}/leads`, { withCredentials: true })
      .then((r) => setLeads(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <DashboardLayout title="Leads" subtitle="Form submissions from your landing page agents.">
      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : leads.length === 0 ? (
        <div className="bg-white rounded-3xl p-10 border border-neutral-200/70 text-center">
          <div className="w-12 h-12 rounded-full bg-neutral-100 flex items-center justify-center mx-auto mb-3">
            <Inbox className="text-neutral-400" size={20} />
          </div>
          <p className="text-neutral-700 font-medium">No leads yet</p>
          <p className="text-[13px] text-neutral-500 mt-1">When someone fills the agent forms on your landing page, they appear here.</p>
        </div>
      ) : (
        <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden">
          <table className="w-full text-[14px]">
            <thead className="bg-neutral-50/50 border-b border-neutral-200/70">
              <tr className="text-left text-[12px] uppercase tracking-wider text-neutral-500">
                <th className="p-4">Agent</th>
                <th className="p-4">Contact</th>
                <th className="p-4">Website</th>
                <th className="p-4">Details</th>
                <th className="p-4">When</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                <tr key={l.id} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50/40">
                  <td className="p-4 capitalize font-medium">{l.agent_id}</td>
                  <td className="p-4">
                    <div className="flex items-center gap-1.5 text-neutral-800"><Mail size={13} /> {l.email}</div>
                    {l.name && <div className="text-[12px] text-neutral-500 mt-0.5">{l.name}</div>}
                  </td>
                  <td className="p-4">
                    {l.website ? <a href={l.website} target="_blank" rel="noreferrer" className="text-[#1B7BFF] inline-flex items-center gap-1 text-[13px]"><Globe size={12} /> Visit</a> : <span className="text-neutral-400">—</span>}
                  </td>
                  <td className="p-4 max-w-xs">
                    {l.platforms?.length > 0 && <div className="text-[12px] text-neutral-600 mb-1">Platforms: {l.platforms.join(', ')}</div>}
                    {l.pain_points && <div className="text-[12px] text-neutral-600 line-clamp-2">{l.pain_points}</div>}
                  </td>
                  <td className="p-4 text-[12px] text-neutral-500">{new Date(l.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </DashboardLayout>
  );
};

export default Leads;
