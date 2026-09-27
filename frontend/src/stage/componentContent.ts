import type {Component} from './voiceEditor';
import {BASE_URL} from '../designer/api';
export const mediaUrl=(url:string)=>url.startsWith('/')?BASE_URL+url:url;
export const escapeHtml=(s:string)=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
export function contentHtml(c:Component){
 const esc=escapeHtml;
 if(c.kind==='image')return c.url?`<img alt="${esc(c.text)}" src="${esc(mediaUrl(c.url))}" style="width:100%;height:100%;object-fit:${c.fit==='cover'?'cover':'contain'}"/>`:`<div style="height:100%;box-sizing:border-box;border:2px dashed #7654ff">▧ ${esc(c.text||'Изображение')}</div>`;
 if(c.kind==='table')return `<table style="width:100%;height:100%;border-collapse:collapse;table-layout:fixed">${(c.rows??[['Заголовок','Значение'],['Строка','']]).map((row,i)=>`<tr>${row.map(cell=>`<${i?'td':'th'} style="border:1px solid currentColor;padding:0.2em;overflow-wrap:anywhere">${esc(cell)}</${i?'td':'th'}>`).join('')}</tr>`).join('')}</table>`;
 if(c.kind==='chart'){
  const values=c.values??[],labels=c.labels??[];const max=Math.max(1,...values);const slot=100/Math.max(1,values.length);
  return `<div style="height:100%;display:flex;align-items:flex-end;gap:2%;padding:4%;box-sizing:border-box">${values.map((value,i)=>`<div style="width:${slot}%;height:100%;display:flex;flex-direction:column;justify-content:flex-end;text-align:center"><span>${esc(String(value))}</span><div style="height:${value/max*75}%;min-height:1px;background:${/^#[0-9a-f]{6}$/i.test(c.fill)?c.fill:'#7654ff'}"></div><span style="font-size:0.7em">${esc(labels[i]??'')}</span></div>`).join('')}</div>`;
 }
 return esc(c.text);
}
