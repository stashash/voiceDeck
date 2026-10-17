import {describe,it,expect} from 'vitest';
import {resolveDesignerBaseUrl} from './baseUrl';

describe('designer base URL',()=>{
  it('uses the host-mapped Designer service on the direct local app port',()=>{
    expect(resolveDesignerBaseUrl({hostname:'localhost',port:'8088'},'/designer')).toBe('http://localhost:8090');
    expect(resolveDesignerBaseUrl({hostname:'127.0.0.1',port:'8088'},'/designer')).toBe('http://127.0.0.1:8090');
  });
  it('keeps the same-origin proxy for public and proxy-local pages',()=>{
    expect(resolveDesignerBaseUrl({hostname:'localhost',port:'8087'},'/designer')).toBe('/designer');
    expect(resolveDesignerBaseUrl({hostname:'voice.example',port:''},'/designer')).toBe('/designer');
  });
  it('respects an explicit service URL',()=>{
    expect(resolveDesignerBaseUrl({hostname:'localhost',port:'8088'},'http://designer:8090')).toBe('http://designer:8090');
  });
});
