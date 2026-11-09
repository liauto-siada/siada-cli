import type { Message } from '../types/index.js';
import { t } from '../i18n/index.js';

export function isHookMessage(message: Message): boolean {
  return message.metadata?.subtype === 'hook' || message.metadata?.eventType === 'hook';
}

export function hookMessageLabel(message: Message): string {
  const status = message.metadata?.hookStatus;
  const label = status === 'blocked' ? t('已拦截', 'Blocked') :
    status === 'stopped' ? t('已中止', 'Stopped') : t('提示', 'Notice');
  return ['Hook', message.metadata?.hookEvent, label].filter(Boolean).join(' · ');
}