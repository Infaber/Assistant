import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
  return {id:"/",name:"Ariana",short_name:"Ariana",description:"Your personal Ariana assistant. Chat, talk, and connect to your Mac.",start_url:"/",scope:"/",display:"standalone",background_color:"#121116",theme_color:"#121116",icons:[{src:"/app-icon",sizes:"512x512",type:"image/png",purpose:"any"}]};
}
