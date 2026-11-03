"use client";
import { useEffect } from "react";
/** Keep the chat composer above Safari's software keyboard and home indicator. */
export default function MobileViewport() {
  useEffect(()=>{
    const viewport=window.visualViewport;
    const update=()=>{
      if(innerWidth<=700 && viewport) {document.documentElement.style.setProperty("--ariana-phone-height",`${viewport.height}px`);document.documentElement.dataset.phoneKeyboard=String(viewport.height<innerHeight*.75);}
      else {document.documentElement.style.removeProperty("--ariana-phone-height");delete document.documentElement.dataset.phoneKeyboard;}
    };
    update();viewport?.addEventListener("resize",update);window.addEventListener("resize",update);
    return()=>{viewport?.removeEventListener("resize",update);window.removeEventListener("resize",update);document.documentElement.style.removeProperty("--ariana-phone-height");delete document.documentElement.dataset.phoneKeyboard;};
  },[]);
  return null;
}
