import {describe,expect,it} from 'vitest';
import {resolveDesignerBaseUrl} from './baseUrl';

describe('resolveDesignerBaseUrl',()=>{
 it('uses the local designer service when the app is opened directly on its local port',()=>{
  expect(resolveDesignerBaseUrl('/designer',{hostname:'localhost',port:'8088'})).toBe('http://localhost:8090');
  expect(resolveDesignerBaseUrl('/designer',{hostname:'127.0.0.1',port:'8088'})).toBe('http://localhost:8090');
 });
 it('keeps same-origin proxy routing for the public app and proxy port',()=>{
  expect(resolveDesignerBaseUrl('/designer',{hostname:'chamomile.ngrok-free.dev',port:''})).toBe('/designer');
  expect(resolveDesignerBaseUrl('/designer',{hostname:'localhost',port:'8087'})).toBe('/designer');
 });
 it('uses the direct local designer by default when no Vite URL is configured',()=>{
  expect(resolveDesignerBaseUrl(undefined)).toBe('http://localhost:8090');
 });
});
