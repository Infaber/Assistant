import {allowedOrigin,hasAccessCode,PHONE_COOKIE,privatePhoneServer} from "./connection-security";
type Environment=Record<string,string|undefined>;
export function phonePairing(request:Request,env:Environment=process.env) {
  const headers={"Cache-Control":"no-store"};
  if(!privatePhoneServer(env))return Response.json({error:"Pairing is available through your Mac’s private iPhone link."},{status:404,headers});
  if(!allowedOrigin(request,env))return Response.json({error:"This request is not allowed."},{status:403,headers});
  if(request.method==="DELETE")return Response.json({paired:false},{headers:{...headers,"Set-Cookie":`${PHONE_COOKIE}=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0`}});
  const code=env.ARIANA_ACCESS_CODE?.trim();
  if(!code || !hasAccessCode(request,code,env,false))return Response.json({error:"This pairing link has expired. Show a new link on your Mac."},{status:401,headers});
  return Response.json({paired:true},{headers:{...headers,"Set-Cookie":`${PHONE_COOKIE}=${encodeURIComponent(code)}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=2592000`}});
}
