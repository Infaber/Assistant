import React,{useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import type {LocalParticipant} from 'livekit-client';
import ChatTranscript,{type ChatMessage} from '../../components/chat-transcript';
import SharingComposer from '../../components/sharing-composer';
function Fixture(){
 const [draft,setDraft]=useState('');const [messages,setMessages]=useState<ChatMessage[]>([]);const [pending,setPending]=useState(false);const input=useRef<HTMLInputElement|HTMLTextAreaElement>(null);
 return <><ChatTranscript active messages={messages} pending={pending}/><SharingComposer multiline participant={{} as LocalParticipant} ready draft={draft} setDraft={setDraft} inputRef={input} sessionKey onShared={()=>{}} onError={()=>{}} onText={async text=>{setMessages(rows=>[...rows,{id:crypto.randomUUID(),isAgent:false,message:text,files:[]}]);setPending(true);await new Promise(resolve=>setTimeout(resolve,20));setMessages(rows=>[...rows,{id:crypto.randomUUID(),isAgent:true,message:`Fixture reply: ${text}`,files:[]}]);setPending(false);}} onSent={()=>input.current?.focus()}/></>;
}
createRoot(document.getElementById('root')!).render(<Fixture/>);
