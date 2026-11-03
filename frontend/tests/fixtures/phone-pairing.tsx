import React,{useCallback} from 'react';
import {createRoot} from 'react-dom/client';
import PhonePairing from '../../components/phone-pairing';
function Fixture(){const onCode=useCallback((code:string)=>{Object.assign(window,{pairedCode:code});},[]);return <PhonePairing onCode={onCode}/>;}
createRoot(document.getElementById('root')!).render(<Fixture/>);
