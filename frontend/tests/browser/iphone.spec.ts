import {test,expect} from '@playwright/test';
import {build} from 'esbuild';
import path from 'node:path';
const fixtureCode='fixture_'.repeat(7);
test('iPhone install metadata and keyboard-sized chat stay usable',async({page,request})=>{
 const response=await request.get('/manifest.webmanifest');expect(response.ok()).toBe(true);const manifest=await response.json();expect(manifest.display).toBe('standalone');expect(manifest.start_url).toBe('/');expect(manifest.icons[0].sizes).toBe('512x512');
 await page.setViewportSize({width:390,height:844});await page.goto('/');
 await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute('href','/app-icon');
 await expect(page.locator('meta[name="mobile-web-app-capable"]')).toHaveAttribute('content','yes');
 await page.getByRole('button',{name:'Conversation',exact:true}).click();await page.setViewportSize({width:390,height:360});
 const composer=page.locator('.input-overlay');await expect(composer).toBeVisible();const bounds=await composer.boundingBox();expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(360);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('Mac iPhone access requires explicit enable and pairing reveal',async({page})=>{
 await page.addInitScript(()=>{
  const calls:unknown[]=[];Object.assign(window,{phoneCalls:calls});let enabled=false;
  window.arianaDesktop={desktop:true,accessCode:'fixture-native',postMessage:message=>{
   calls.push(message);if(message.type==='iphone-settings')enabled=message.enabled;
   if(message.type==='iphone-status'||message.type==='iphone-settings')window.dispatchEvent(new CustomEvent('ariana:iphone-status',{detail:{enabled,installed:true,ready:enabled,phase:enabled?'ready':'off',message:enabled?'Ready to pair your iPhone.':'iPhone access is off.',...(enabled?{url:'https://mac.fixture.ts.net:8443'}:{}),...(message.type==='iphone-status'&&message.reveal?{code:'fixture_'.repeat(7),qr:'data:image/png;base64,fixture'}:{})}}));
  }};
 });
 await page.route('**/api/connection',route=>route.fulfill({status:503,json:{error:'Offline fixture'}}));await page.goto('/');await page.getByRole('button',{name:'Settings',exact:true}).click();
 await expect(page.getByText('iPhone access is off.',{exact:true})).toBeVisible();
 const calls=()=>page.evaluate(()=>(window as unknown as {phoneCalls:{type:string;reveal?:boolean}[]}).phoneCalls);
 expect((await calls()).filter(call=>call.type==='iphone-settings')).toEqual([]);
 await page.getByRole('button',{name:'Enable private iPhone access',exact:true}).click();await expect(page.getByRole('button',{name:'Show iPhone pairing',exact:true})).toBeVisible();expect((await calls()).some(call=>call.reveal)).toBe(false);
 await page.getByRole('button',{name:'Show iPhone pairing',exact:true}).click();await expect(page.getByAltText('Scan with your iPhone camera to pair Ariana')).toBeVisible();
 await page.getByRole('button',{name:'Hide pairing',exact:true}).click();await expect(page.getByAltText('Scan with your iPhone camera to pair Ariana')).toHaveCount(0);
 await page.getByRole('button',{name:'Turn off iPhone access',exact:true}).click();await expect(page.getByText('iPhone access is off.',{exact:true})).toBeVisible();
});
test('saved phone pairing authorizes text connection and can be forgotten',async({page})=>{
 let authorization='';await page.addInitScript(code=>localStorage.setItem('ariana.phone.pairing',code),fixtureCode);
 await page.route('**/api/connection',route=>{authorization=route.request().headers().authorization;return route.fulfill({status:503,json:{error:'Phone connection fixture'}});});
 await page.goto('/');await page.getByRole('button',{name:'Conversation',exact:true}).click();await page.getByRole('button',{name:'Connect with text',exact:true}).click();
 await expect(page.getByText('Phone connection fixture',{exact:true}).last()).toBeVisible();expect(authorization).toBe(`Bearer ${fixtureCode}`);
 await page.getByRole('button',{name:'Settings',exact:true}).click();await page.getByRole('button',{name:'Remove saved phone pairing',exact:true}).click();await expect.poll(()=>page.evaluate(()=>localStorage.getItem('ariana.phone.pairing'))).toBeNull();
});

test('QR pairing needs confirmation, removes the fragment and never sends its key in URLs',async({page})=>{
 const seen:string[]=[];
 const bundle=(await build({entryPoints:[path.resolve("tests/fixtures/phone-pairing.tsx")],bundle:true,write:false,platform:"browser",format:"iife",jsx:"automatic"})).outputFiles[0].text;
 await page.route('https://mac.fixture.ts.net:8443/**',async route=>{
  seen.push(route.request().url());
  if(route.request().url().endsWith('/api/phone-pairing')) {
   expect(route.request().headers().authorization).toBe(`Bearer ${fixtureCode}`);
   await route.fulfill({status:200,contentType:'application/json',headers:{'Set-Cookie':`__Host-ariana-phone=${fixtureCode}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=2592000`},body:'{"paired":true}'});return;
  }
  await route.fulfill({contentType:"text/html",body:'<!doctype html><div id="root"></div><script>'+bundle.replaceAll('</script','<\\/script')+'</script>'});
 });
 await page.goto(`https://mac.fixture.ts.net:8443/#pair=${fixtureCode}`);
 await expect(page.getByRole('dialog',{name:'Pair Ariana on this iPhone'})).toBeVisible();
 expect(await page.evaluate(()=>localStorage.getItem('ariana.phone.pairing'))).toBeNull();
 expect(new URL(page.url()).hash).toBe('');
 await page.getByRole('button',{name:'Pair this iPhone',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Pair Ariana on this iPhone'})).not.toBeVisible();
 expect(await page.evaluate(()=>localStorage.getItem('ariana.phone.pairing'))).toBeNull();
 const cookie=(await page.context().cookies()).find(cookie=>cookie.name==='__Host-ariana-phone');expect(cookie?.httpOnly).toBe(true);expect(cookie?.secure).toBe(true);
 expect(await page.evaluate(()=>document.cookie)).not.toContain(fixtureCode);
 expect(seen.every(url=>!url.includes(fixtureCode))).toBe(true);
 await page.context().clearCookies();await page.evaluate(code=>{location.hash=`pair=${code}`;},fixtureCode);
 await expect(page.getByRole('dialog',{name:'Pair Ariana on this iPhone'})).toBeVisible();
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Pair Ariana on this iPhone'})).not.toBeVisible();
 expect((await page.context().cookies()).find(cookie=>cookie.name==='__Host-ariana-phone')).toBeUndefined();
 expect(seen.filter(url=>url.endsWith('/api/phone-pairing')).length).toBe(1);
});
test('Safari visual viewport keeps the composer above the software keyboard',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');await page.getByRole('button',{name:'Conversation',exact:true}).click();
 await page.evaluate(()=>{Object.defineProperty(window.visualViewport,'height',{configurable:true,value:350});window.visualViewport?.dispatchEvent(new Event('resize'));});
 await expect(page.locator('html')).toHaveAttribute('data-phone-keyboard','true');
 const bounds=await page.locator('.input-overlay').boundingBox();expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(350);
});
