"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowDown, MessageSquare } from "lucide-react";
import { assistantName } from "../lib/persona";
export type ChatMessage = {id: string; isAgent: boolean; message: string; files: {name: string; preview?: string}[]};

export default function ChatTranscript({messages, pending, active}: {messages: ChatMessage[]; pending: boolean; active: boolean}) {
  const scroll = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const [away, setAway] = useState(false);
  const latest = messages.at(-1);
  function toLatest() {const element=scroll.current;if(element){element.scrollTop=element.scrollHeight;following.current=true;setAway(false);}}
  useEffect(() => {if(active) toLatest();}, [active]);
  useEffect(() => {if(active && following.current) toLatest();}, [active, messages.length, latest?.message, pending]);
  return <div className="chat-scroll" ref={scroll} onScroll={() => {
    const element=scroll.current!;following.current=element.scrollHeight-element.scrollTop-element.clientHeight<80;setAway(!following.current);
  }}>
    <div className="chat-messages" role="log" aria-label="Chat messages" aria-relevant="additions text">
      {!messages.length && <div className="chat-welcome"><MessageSquare size={30}/><h2>What’s on your mind?</h2><p>Write to {assistantName}. Your voice and text conversation live together here.</p></div>}
      {messages.map(message => <article className={`chat-message ${message.isAgent ? "from-ariana" : "from-you"}`} key={message.id}>
        <span className="chat-author">{message.isAgent ? assistantName : "You"}</span>
        <div className="chat-message-content"><p>{message.message}</p>{message.files.map((file,index)=><div className="shared-file" key={index}>{file.preview && <img src={file.preview} alt={file.name}/>}<span>{file.name}</span></div>)}</div>
      </article>)}
      {pending && <p className="chat-pending" role="status"><span/>{assistantName} is thinking…</p>}
    </div>
    {away && <button className="chat-latest" onClick={toLatest}><ArrowDown size={15}/>Latest messages</button>}
  </div>;
}
