import { useNavigate } from 'react-router-dom';
import { useToast } from './use-toast';

/**
 * handlePaywall — call from a catch block to show a friendly upgrade prompt
 * whenever the backend responds with 402 (plan-gating error). Returns true
 * if the error was a paywall (so the caller can `return`), false otherwise.
 */
export const usePaywallHandler = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  return (err) => {
    if (err?.response?.status === 402) {
      const detail = err.response.data?.detail || {};
      toast({
        title: detail.code === 'channel_limit_reached'
          ? 'Channel limit reached'
          : 'AI limit reached',
        description: detail.message || 'Upgrade your plan to continue.',
        action: undefined,
      });
      setTimeout(() => navigate('/pricing'), 1200);
      return true;
    }
    return false;
  };
};
