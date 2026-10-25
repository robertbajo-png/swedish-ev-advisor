export const SITE_NAME = 'Elbilsagenten';
export const SITE_ORIGIN = 'https://elbilsagenten.se';

export function operatorInfo(env = {}) {
  const name = String(env.VITE_OPERATOR_NAME || '').trim();
  const email = String(env.VITE_CONTACT_EMAIL || '').trim();
  const organizationNumber = String(env.VITE_OPERATOR_ORG_NUMBER || '').trim();
  const configured = name.length >= 2 && name.length <= 160 && !/[\r\n]/.test(name)
    && email.length <= 254 && /^[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+$/.test(email)
    && !/@(?:example\.(?:com|org|net)|[^@]*\.(?:example|test))$/i.test(email);
  return { name, email, organizationNumber, configured,
    emailHref: configured ? 'mailto:' + encodeURIComponent(email).replace('%40', '@') : null };
}

export const PUBLIC_OPERATOR = operatorInfo(import.meta.env || {});
