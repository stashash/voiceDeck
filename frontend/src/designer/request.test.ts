import {afterEach,expect,it,vi} from 'vitest';
import {request} from './request';
afterEach(()=>vi.unstubAllGlobals());
it('terminates an unresponsive request without replaying the mutation',async()=>{
  const fetch=vi.fn((_url,init)=>new Promise((_resolve,reject)=>{
    init.signal.addEventListener('abort',()=>reject(init.signal.reason));
  }));
  vi.stubGlobal('fetch',fetch);
  await expect(request('/edit',{method:'POST'},15)).rejects.toMatchObject({name:'TimeoutError'});
  expect(fetch).toHaveBeenCalledTimes(1);
});
