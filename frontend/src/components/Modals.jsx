import React, { useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { useToast } from '../hooks/use-toast';
import { ArrowLeft, Send, Loader2 } from 'lucide-react';
import { agentsList } from '../data/mock';
import { API } from '../context/AuthContext';

const SelectAgentModal = ({ open, onClose, onSelect }) => {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl bg-white rounded-3xl border-0 p-0 overflow-hidden">
        <div className="p-8">
          <DialogHeader>
            <DialogTitle className="text-3xl font-medium tracking-tight text-neutral-900">Choose Your Specialist</DialogTitle>
            <DialogDescription className="text-neutral-600 mt-1">Select the AI marketer you'd like to work with</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-7">
            {agentsList.map((a) => (
              <button
                key={a.id}
                onClick={() => onSelect(a)}
                className={`group bg-gradient-to-br ${a.color} rounded-2xl p-5 flex flex-col items-center text-center hover:-translate-y-1 transition-all duration-300 border border-neutral-200/50 hover:shadow-lg`}
              >
                <div className="w-20 h-20 rounded-full overflow-hidden mb-3 ring-4 ring-white shadow-sm">
                  <img src={a.img} alt={a.name} className="w-full h-full object-cover" />
                </div>
                <div className="text-[11px] uppercase tracking-wider text-neutral-700 font-medium">{a.role}</div>
                <div className="text-lg font-semibold text-neutral-900 mt-0.5">{a.name}</div>
                <div className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-[#1B7BFF] opacity-90 group-hover:opacity-100">
                  Message me
                </div>
              </button>
            ))}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

const AgentChatModal = ({ open, onClose, agent, onBack }) => {
  const { toast } = useToast();
  const [form, setForm] = useState({});
  const [platforms, setPlatforms] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  if (!agent) return null;

  const handleSend = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await axios.post(
        `${API}/leads`,
        {
          agent_id: agent.id,
          name: form.name,
          email: form.email,
          website: form.website,
          platforms,
          pain_points: form.pain,
          competitors: form.comp,
          keywords: form.kw,
          email_platform: form.platform,
        },
        { withCredentials: true }
      );
      toast({
        title: `Message sent to ${agent.name}!`,
        description: `${agent.name} will reach out within 24 hours.`,
      });
      setForm({});
      setPlatforms([]);
      onClose();
    } catch (err) {
      toast({ title: 'Could not send', description: err.response?.data?.detail || 'Please try again.' });
    } finally {
      setSubmitting(false);
    }
  };

  const togglePlatform = (p) => {
    setPlatforms((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]);
  };

  const intros = {
    nova: "If you need more traffic but struggle to rank, post consistently, or make sense of your analytics, I can help build the engine that delivers it.",
    sam: "I handle SEO and GEO content marketing — from keyword research to publishing articles optimized for Google and AI search engines.",
    kai: "If you're looking to accelerate your social media presence, fill in the information below. Can't wait to learn more about your business.",
    angela: "I write, design, and schedule your email campaigns while you run your business. No dashboard, no new tool — manage me from your inbox.",
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg bg-white rounded-3xl border-0 p-0 overflow-hidden">
        <DialogTitle className="sr-only">Chat with {agent?.name || 'AI agent'}</DialogTitle>
        <div className="p-7">
          <button onClick={onBack} className="text-[13px] text-neutral-500 hover:text-neutral-800 flex items-center gap-1 mb-4">
            <ArrowLeft size={14} /> Choose another
          </button>

          <div className="flex items-center gap-4 mb-5">
            <div className={`w-14 h-14 rounded-full overflow-hidden ring-4 ring-white shadow-sm bg-gradient-to-br ${agent.color}`}>
              <img src={agent.img} alt={agent.name} className="w-full h-full object-cover" />
            </div>
            <div>
              <div className="text-lg font-semibold text-neutral-900">{agent.name}</div>
              <div className="flex items-center gap-1.5 text-[12px] text-emerald-600 font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Active now
              </div>
            </div>
          </div>

          <p className="text-[14px] text-neutral-700 leading-relaxed mb-5">
            Great to meet you! I'm {agent.name}. {intros[agent.id]} Fill in the details below and I'll take it from here.
          </p>

          <form onSubmit={handleSend} className="space-y-4">
            {agent.id === 'nova' && (
              <Field label="Your Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} placeholder="Jane Doe" required />
            )}
            <Field label="Work Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} placeholder="you@company.com" required />
            <Field label="Website URL" value={form.website} onChange={(v) => setForm({ ...form, website: v })} placeholder="https://yoursite.com" required />

            {agent.id === 'kai' && (
              <div>
                <Label className="text-[13px] font-medium text-neutral-700 mb-2 block">Platforms to Monitor (select at least one)</Label>
                <div className="flex flex-wrap gap-2">
                  {['Instagram', 'TikTok', 'X (Twitter)', 'Reddit'].map((p) => (
                    <button type="button" key={p} onClick={() => togglePlatform(p)} className={`px-3.5 py-1.5 rounded-full text-[13px] font-medium border transition-all ${platforms.includes(p) ? 'bg-[#1B7BFF] text-white border-[#1B7BFF]' : 'bg-white text-neutral-700 border-neutral-300 hover:border-neutral-400'}`}>
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {agent.id === 'kai' && (
              <>
                <Field label="Competitors (Optional)" value={form.comp} onChange={(v) => setForm({ ...form, comp: v })} placeholder="competitor1.com, competitor2.com" />
                <Field label="Keywords (Optional)" value={form.kw} onChange={(v) => setForm({ ...form, kw: v })} placeholder="e.g. sustainable fashion" />
              </>
            )}

            {agent.id === 'angela' && (
              <div>
                <Label className="text-[13px] font-medium text-neutral-700 mb-2 block">Email platform (Optional)</Label>
                <Select onValueChange={(v) => setForm({ ...form, platform: v })}>
                  <SelectTrigger className="rounded-xl border-neutral-300 h-11">
                    <SelectValue placeholder="Select an option" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="klaviyo">Klaviyo</SelectItem>
                    <SelectItem value="mailchimp">Mailchimp</SelectItem>
                    <SelectItem value="activecampaign">ActiveCampaign</SelectItem>
                    <SelectItem value="constant">Constant Contact</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}

            {agent.id === 'nova' && (
              <div>
                <Label className="text-[13px] font-medium text-neutral-700 mb-2 block">What are your top 3 pain points?</Label>
                <Textarea
                  value={form.pain || ''}
                  onChange={(e) => setForm({ ...form, pain: e.target.value })}
                  placeholder="e.g. low organic traffic, inconsistent posting..."
                  className="rounded-xl border-neutral-300"
                  rows={3}
                />
              </div>
            )}

            <button type="submit" disabled={submitting} className="w-full bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-60 text-white rounded-full py-3 text-[14px] font-medium inline-flex items-center justify-center gap-2 transition-colors">
              {submitting ? <Loader2 size={15} className="animate-spin" /> : <>Send <Send size={15} /></>}
            </button>
          </form>
        </div>
      </DialogContent>
    </Dialog>
  );
};

const Field = ({ label, value, onChange, ...props }) => (
  <div>
    <Label className="text-[13px] font-medium text-neutral-700 mb-2 block">{label}</Label>
    <Input value={value || ''} onChange={(e) => onChange(e.target.value)} className="rounded-xl border-neutral-300 h-11" {...props} />
  </div>
);

export { SelectAgentModal, AgentChatModal };
