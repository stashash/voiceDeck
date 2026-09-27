import {VoiceEditor} from './voiceEditor';
import {escapeHtml} from './componentContent';
export function deckHtml(editor:VoiceEditor){
 const copy=new VoiceEditor();copy.document=structuredClone(editor.document);
 const frames=copy.document.pages.map((_,index)=>{copy.document.index=index;const slide=copy.slide();return `<section><iframe sandbox="" title="Слайд ${index+1}" srcdoc="${escapeHtml(slide.html??'')}"></iframe><small>${escapeHtml(slide.notes??'')}</small></section>`;}).join('');
 return `<!doctype html><html lang="ru"><meta charset="utf-8"><title>VoiceDeck</title><style>body{margin:0;background:#17141f;color:white;font:16px Arial}section{margin:24px auto;max-width:1280px;break-after:page}iframe{width:100%;aspect-ratio:16/9;border:0;display:block}small{display:block;padding:8px}@media print{body{background:white;color:black}section{margin:0}small{font-size:8px}}</style>${frames}</html>`;
}
export function downloadDeck(editor:VoiceEditor,format:'html'|'json'){
 const blob=new Blob([format==='html'?deckHtml(editor):JSON.stringify(editor.document,null,2)],{type:format==='html'?'text/html;charset=utf-8':'application/json'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`VoiceDeck.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
