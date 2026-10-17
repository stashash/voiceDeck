const LOCAL_DESIGNER_URL='http://localhost:8090';

export function resolveDesignerBaseUrl(
 configured:string|undefined,
 location?:Pick<Location,'hostname'|'port'>,
):string{
 if(configured==='/designer'&&location&&['localhost','127.0.0.1'].includes(location.hostname)&&location.port==='8088')return LOCAL_DESIGNER_URL;
 return configured??LOCAL_DESIGNER_URL;
}
