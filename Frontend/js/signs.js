/* signs.js — Sign dictionary browsing and search helpers */

import { Api } from './api.js';

export async function fetchSignCatalog() {
  const data = await Api.getSigns();
  return data.signs || [];
}

export function filterSigns(signs, { query = '', category = 'all' } = {}) {
  const q = query.trim().toLowerCase();
  return signs.filter(s => {
    const catMatch = category === 'all' || (s.category && s.category.toLowerCase() === category.toLowerCase());
    const qMatch = !q ||
      (s.sign_name && s.sign_name.toLowerCase().includes(q)) ||
      (s.sign_meaning && s.sign_meaning.toLowerCase().includes(q)) ||
      (String(s.class_id).includes(q));
    return catMatch && qMatch;
  });
}
