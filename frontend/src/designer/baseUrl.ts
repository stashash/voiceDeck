const env=(import.meta as unknown as {env?:Record<string,string|undefined>}).env??{};

/** Use the public reverse proxy by default, but the host-mapped Designer port for direct local access. */
export function resolveDesignerBaseUrl(location:{hostname:string;port:string},configured=env.VITE_DESIGNER_URL??'http://localhost:8090'){
  const localHost=location.hostname==='localhost'||location.hostname==='127.0.0.1';
  if(configured==='/designer'&&localHost&&location.port!=='8087')return `http://${location.hostname}:8090`;
  return configured;
}

export const DESIGNER_BASE_URL=resolveDesignerBaseUrl(typeof window==='undefined'?{hostname:'',port:''}:window.location);
