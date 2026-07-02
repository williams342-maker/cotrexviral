import React, { useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '../../components/ui/dialog';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Button } from '../../components/ui/button';
import { Loader2, Check, ExternalLink } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/**
 * WordPress self-hosted connect dialog — Option A (Application Passwords).
 *
 * Flow:
 *   1. User pastes site URL + username + app password.
 *   2. "Test connection" hits POST /api/wordpress/test (no persistence).
 *   3. On success, "Connect" hits POST /api/wordpress/connect (persists
 *      an encrypted credential row).
 */
const WordPressConnectDialog = ({ open, onOpenChange, onConnected }) => {
  const [siteUrl, setSiteUrl]       = useState('');
  const [username, setUsername]     = useState('');
  const [appPassword, setAppPass]   = useState('');
  const [testing, setTesting]       = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [tested, setTested]         = useState(null);   // { wp_user_name, wp_roles, site_url }
  const [error, setError]           = useState(null);
  const { toast } = useToast();

  const reset = () => {
    setSiteUrl(''); setUsername(''); setAppPass('');
    setTested(null); setError(null); setTesting(false); setConnecting(false);
  };

  const handleClose = (v) => {
    if (!v) reset();
    onOpenChange(v);
  };

  const payload = () => ({
    site_url:             siteUrl.trim(),
    username:             username.trim(),
    application_password: appPassword.trim(),
  });

  const canSubmit = siteUrl.trim() && username.trim() && appPassword.trim();

  const runTest = async () => {
    setError(null);
    setTested(null);
    setTesting(true);
    try {
      const r = await axios.post(`${API}/wordpress/test`, payload(), { withCredentials: true });
      setTested(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Connection test failed.');
    } finally {
      setTesting(false);
    }
  };

  const runConnect = async () => {
    setError(null);
    setConnecting(true);
    try {
      const r = await axios.post(`${API}/wordpress/connect`, payload(), { withCredentials: true });
      toast({
        title: 'WordPress connected',
        description: `Publishing as ${r.data.wp_user_name} on ${r.data.site_url}.`,
      });
      reset();
      onConnected && onConnected();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Connection failed.');
    } finally {
      setConnecting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[520px]" data-testid="wp-connect-dialog">
        <DialogHeader>
          <DialogTitle>Connect WordPress (Self-Hosted)</DialogTitle>
          <DialogDescription>
            Uses an Application Password — no plugin required. Works on any WordPress 5.6+ site over HTTPS.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="wp-site" className="text-[13px]">WordPress site URL</Label>
            <Input
              id="wp-site"
              type="url"
              placeholder="https://example.com"
              value={siteUrl}
              onChange={(e) => { setSiteUrl(e.target.value); setTested(null); }}
              data-testid="wp-site-input"
            />
            <p className="text-[11.5px] text-neutral-500">Must be https:// — Basic Auth over plain HTTP is refused.</p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="wp-user" className="text-[13px]">WordPress username</Label>
            <Input
              id="wp-user"
              type="text"
              placeholder="e.g. jane_editor"
              autoComplete="username"
              value={username}
              onChange={(e) => { setUsername(e.target.value); setTested(null); }}
              data-testid="wp-username-input"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="wp-app" className="text-[13px]">Application Password</Label>
            <Input
              id="wp-app"
              type="password"
              placeholder="xxxx xxxx xxxx xxxx xxxx xxxx"
              autoComplete="off"
              value={appPassword}
              onChange={(e) => { setAppPass(e.target.value); setTested(null); }}
              data-testid="wp-app-password-input"
            />
            <p className="text-[11.5px] text-neutral-500 leading-relaxed">
              Generate one at{' '}
              <a
                href={siteUrl ? `${siteUrl.replace(/\/$/, '')}/wp-admin/profile.php#application-passwords-section` : 'https://wordpress.org/documentation/article/application-passwords/'}
                target="_blank"
                rel="noreferrer"
                className="text-[#1B7BFF] hover:underline inline-flex items-center gap-0.5"
              >
                Users → Profile → Application Passwords <ExternalLink size={11} />
              </a>
              . Store safely — it&apos;s shown only once.
            </p>
          </div>

          {tested && (
            <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-[12.5px] text-emerald-900" data-testid="wp-test-success">
              <div className="flex items-center gap-1.5 font-medium mb-0.5">
                <Check size={14} /> Verified as <span className="font-semibold">{tested.wp_user_name}</span>
              </div>
              <div className="text-emerald-800 text-[11.5px]">
                Roles: {(tested.wp_roles || []).join(', ') || '—'}
              </div>
            </div>
          )}
          {error && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-[12.5px] text-rose-900" data-testid="wp-connect-error">
              {error}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={runTest}
            disabled={!canSubmit || testing || connecting}
            data-testid="wp-test-btn"
          >
            {testing ? <Loader2 size={14} className="animate-spin mr-1.5" /> : null}
            Test connection
          </Button>
          <Button
            type="button"
            onClick={runConnect}
            disabled={!canSubmit || !tested || connecting || testing}
            className="bg-[#1B7BFF] hover:bg-[#1668e0]"
            data-testid="wp-connect-btn"
          >
            {connecting ? <Loader2 size={14} className="animate-spin mr-1.5" /> : null}
            Connect
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default WordPressConnectDialog;
