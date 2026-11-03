import {phonePairing} from "@/lib/phone-auth";
export const runtime="nodejs";
export const dynamic="force-dynamic";
export function POST(request:Request){return phonePairing(request);}
export function DELETE(request:Request){return phonePairing(request);}
