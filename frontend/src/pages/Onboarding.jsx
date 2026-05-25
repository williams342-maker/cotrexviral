import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Loader2, ArrowRight, CheckCircle2, Globe, Sparkles, Target, Zap } from 'lucide-react';
import { useAuth, API } from '../context/AuthContext';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import { useToast } from '../hooks/use-toast';

const Onboarding = () => {
  const navigate = useNavigate();
  const { user, refresh } = useAuth();
  const { toast } = useToast();
  const [options, setOptions] = useState({ niches: [], goals: [], platforms: [] });
  const [form, setForm] = useState({
    website: '',
    brand_name: '',
    niche: '',
    goals: [],
    platforms: [],
    challenge: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [skipped, setSkipped] = useState(false);

  useEffect(() => {
    axios.get(`${API}/onboarding/options`, { withCredentials: true })
      .then((r) => setOptions(r.data))
      .catch(() => {});
    axios.get(`${API}/onboarding/me`, { withCredentials: true })
      .then((r) => {
        const p = r.data?.profile || {};
        if (p.website || p.brand_name) setForm((f) => ({ ...f, ...p }));
      })
      .catch(() => {});
  }, []);

  const toggle = (key, value) => {
    setForm((f) => ({
      ...f,
      [key]: f[key].includes(value) ? f[key].filter((x) => x !== value) : [...f[key], value],
    }));
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!form.website.trim() || !form.brand_name.trim() || !form.niche) {
      toast({ title: 'Please complete the required fields' });
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/onboarding`, form, { withCredentials: true });
      await refresh();
      toast({
        title: '✨ You\'re all set!',
        description: 'Our team will reach out with niche-specific tips shortly.',
      });
      navigate('/dashboard');
    } catch (err) {
      toast({
        title: 'Submission failed',
        description: err?.response?.data?.detail || 'Please try again.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const skip = () => {
    sessionStorage.setItem('onboarding_skipped', '1');
    setSkipped(true);
    navigate('/dashboard');
  };

  if (skipped) return null;

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0c0a1f] via-[#1a1442] to-[#0c0a1f] text-white">
      <div className="max-w-2xl mx-auto px-6 py-12 sm:py-20">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-violet-500/15 border border-violet-400/30 text-violet-200 text-[11px] uppercase tracking-wider font-semibold mb-5">
            <Sparkles size={11} /> Welcome, {(user?.name || 'creator').split(' ')[0]}
          </div>
          <h1 className="text-4xl sm:text-5xl font-medium tracking-tight mb-3">
            Let's tailor CortexViral <span className="bg-gradient-to-r from-violet-300 to-cyan-300 bg-clip-text text-transparent">to your brand</span>
          </h1>
          <p className="text-[15px] text-neutral-300 leading-relaxed max-w-lg mx-auto">
            Two minutes now saves hours of generic AI later. Our team also uses these answers to reach out with niche-specific playbooks.
          </p>
        </div>

        <form onSubmit={submit} className="space-y-6 bg-white/[0.04] border border-white/10 backdrop-blur-xl rounded-3xl p-7 sm:p-9">
          {/* Required: website + brand */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FieldDark
              icon={Globe}
              label="Website URL"
              required
              value={form.website}
              onChange={(v) => setForm({ ...form, website: v })}
              placeholder="cortexviral.com"
              testid="onboarding-website"
            />
            <FieldDark
              icon={Sparkles}
              label="Brand / business name"
              required
              value={form.brand_name}
              onChange={(v) => setForm({ ...form, brand_name: v })}
              placeholder="CortexViral"
              testid="onboarding-brand"
            />
          </div>

          {/* Required: niche */}
          <div>
            <Label className="text-[12px] uppercase tracking-wider text-neutral-400 font-semibold mb-2.5 flex items-center gap-1.5">
              <Target size={11} /> Primary niche <span className="text-rose-400">*</span>
            </Label>
            <div className="flex flex-wrap gap-2" data-testid="onboarding-niche-pills">
              {options.niches.map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setForm({ ...form, niche: n })}
                  data-testid={`niche-${n.replace(/[^a-z]/gi, '').toLowerCase()}`}
                  className={`px-3.5 h-9 rounded-full text-[13px] font-semibold border transition-all ${
                    form.niche === n
                      ? 'bg-violet-500 text-white border-violet-500 shadow-lg shadow-violet-500/30'
                      : 'bg-white/5 text-neutral-300 border-white/15 hover:bg-white/10 hover:border-white/30'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* Optional: goals */}
          <div>
            <Label className="text-[12px] uppercase tracking-wider text-neutral-400 font-semibold mb-2.5 flex items-center gap-1.5">
              <Zap size={11} /> What's your main goal? <span className="text-neutral-500 normal-case font-normal tracking-normal">(pick any)</span>
            </Label>
            <div className="flex flex-wrap gap-2" data-testid="onboarding-goals">
              {options.goals.map((g) => (
                <button
                  key={g}
                  type="button"
                  onClick={() => toggle('goals', g)}
                  className={`px-3.5 h-9 rounded-full text-[13px] font-semibold border transition-all ${
                    form.goals.includes(g)
                      ? 'bg-emerald-500/90 text-white border-emerald-500'
                      : 'bg-white/5 text-neutral-300 border-white/15 hover:bg-white/10'
                  }`}
                >
                  {g}
                </button>
              ))}
            </div>
          </div>

          {/* Optional: platforms */}
          <div>
            <Label className="text-[12px] uppercase tracking-wider text-neutral-400 font-semibold mb-2.5">
              Primary platforms <span className="text-neutral-500 normal-case font-normal tracking-normal">(pick any)</span>
            </Label>
            <div className="flex flex-wrap gap-2" data-testid="onboarding-platforms">
              {options.platforms.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => toggle('platforms', p)}
                  className={`px-3.5 h-9 rounded-full text-[13px] font-semibold border transition-all ${
                    form.platforms.includes(p)
                      ? 'bg-cyan-500/90 text-white border-cyan-500'
                      : 'bg-white/5 text-neutral-300 border-white/15 hover:bg-white/10'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Optional: challenge */}
          <div>
            <Label className="text-[12px] uppercase tracking-wider text-neutral-400 font-semibold mb-2.5">
              Biggest content challenge <span className="text-neutral-500 normal-case font-normal tracking-normal">(optional)</span>
            </Label>
            <Textarea
              value={form.challenge}
              onChange={(e) => setForm({ ...form, challenge: e.target.value })}
              placeholder="e.g. We post 3x/week but our hooks aren't getting past 1k views — we keep talking about features instead of outcomes."
              rows={3}
              className="bg-white/5 border-white/15 text-white placeholder:text-neutral-500 focus-visible:ring-violet-500/40"
              data-testid="onboarding-challenge"
            />
          </div>

          {/* Submit / Skip */}
          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <button
              type="submit"
              disabled={submitting}
              data-testid="onboarding-submit"
              className="flex-1 inline-flex items-center justify-center gap-2 bg-gradient-to-r from-violet-500 to-indigo-500 hover:from-violet-400 hover:to-indigo-400 text-white text-[14px] font-semibold h-12 rounded-full transition-all shadow-lg shadow-violet-500/30 disabled:opacity-60"
            >
              {submitting ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
              {submitting ? 'Saving…' : 'Finish setup'}
              {!submitting && <ArrowRight size={15} />}
            </button>
            <button
              type="button"
              onClick={skip}
              data-testid="onboarding-skip"
              className="sm:w-auto text-[13px] font-medium text-neutral-400 hover:text-neutral-200 h-12 px-4 rounded-full"
            >
              Skip for now
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const FieldDark = ({ icon: Icon, label, required, value, onChange, placeholder, testid }) => (
  <div>
    <Label className="text-[12px] uppercase tracking-wider text-neutral-400 font-semibold mb-2.5 flex items-center gap-1.5">
      {Icon && <Icon size={11} />} {label} {required && <span className="text-rose-400">*</span>}
    </Label>
    <Input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      data-testid={testid}
      className="bg-white/5 border-white/15 text-white placeholder:text-neutral-500 focus-visible:ring-violet-500/40 h-11"
    />
  </div>
);

export default Onboarding;
