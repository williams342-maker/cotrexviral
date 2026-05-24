import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Instagram, Twitter, Facebook, Linkedin, Loader2, Check } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

const PLATFORM_META = {
  instagram: { icon: Instagram, label: 'Instagram', color: 'from-pink-500 to-amber-500' },
  tiktok: { icon: () => <span className="text-2xl font-bold">T</span>, label: 'TikTok', color: 'from-neutral-900 to-neutral-700' },
  x: { icon: Twitter, label: 'X (Twitter)', color: 'from-neutral-900 to-neutral-700' },
  facebook: { icon: Facebook, label: 'Facebook', color: 'from-blue-600 to-blue-500' },
  linkedin: { icon: Linkedin, label: 'LinkedIn', color: 'from-sky-700 to-sky-600' },
  reddit: { icon: () => <span className="text-xl font-bold">R</span>, label: 'Reddit', color: 'from-orange-600 to-orange-500' },
};

const Channels = () => {
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/channels`, { withCredentials: true });
      setChannels(r.data);
    } catch (e) {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const toggle = async (ch) => {
    setBusy(ch.platform);
    try {
      if (ch.connected) {
        await axios.post(`${API}/channels/disconnect`, { platform: ch.platform }, { withCredentials: true });
        toast({ title: `Disconnected from ${PLATFORM_META[ch.platform].label}` });
      } else {
        await axios.post(`${API}/channels/connect`, { platform: ch.platform }, { withCredentials: true });
        toast({ title: `Connected to ${PLATFORM_META[ch.platform].label}`, description: 'MOCKED — no real OAuth in this demo.' });
      }
      await load();
    } catch (e) {
      toast({ title: 'Action failed' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <DashboardLayout title="Social Channels" subtitle="Connect your accounts so Automatex can push new listings and posts. (Demo: connection is mocked.)">
      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {channels.map((ch) => {
            const meta = PLATFORM_META[ch.platform];
            const Icon = meta.icon;
            return (
              <div key={ch.platform} className="bg-white rounded-3xl p-6 border border-neutral-200/70">
                <div className="flex items-center gap-3 mb-4">
                  <div className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${meta.color} text-white flex items-center justify-center`}>
                    <Icon size={20} />
                  </div>
                  <div>
                    <div className="text-[15px] font-semibold">{meta.label}</div>
                    <div className="text-[12px] text-neutral-500">
                      {ch.connected ? (ch.handle || 'Connected') : 'Not connected'}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => toggle(ch)}
                  disabled={busy === ch.platform}
                  className={`w-full h-10 rounded-xl text-[13.5px] font-medium inline-flex items-center justify-center gap-2 transition-colors ${
                    ch.connected
                      ? 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
                      : 'bg-[#1B7BFF] hover:bg-[#1668e0] text-white'
                  }`}
                >
                  {busy === ch.platform ? <Loader2 size={14} className="animate-spin" /> : ch.connected ? <><Check size={14} /> Connected</> : 'Connect'}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </DashboardLayout>
  );
};

export default Channels;
