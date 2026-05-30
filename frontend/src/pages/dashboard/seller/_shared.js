import { Mail, Instagram, Facebook, Globe } from 'lucide-react';

export const CHANNEL_ICONS = {
  email: Mail, instagram_dm: Instagram, facebook_message: Facebook,
  linkedin_inmail: Globe, contact_form: Globe,
};

export const EVENT_TONE = {
  sent:            'text-blue-300',
  delivered:       'text-blue-300',
  opened:          'text-amber-300',
  replied:         'text-emerald-300',
  interested:      'text-emerald-300',
  bounced:         'text-rose-300',
  unsubscribed:    'text-rose-300',
  not_interested:  'text-zinc-500',
};
