import {test,expect} from '@playwright/test';
import {build} from 'esbuild';
import path from 'node:path';
let bundle:string;
test.beforeAll(async()=>{bundle=(await build({entryPoints:[path.resolve('tests/fixtures/session-panel.tsx')],bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic'})).outputFiles[0].text;});
test.beforeEach(async({page})=>{await page.route('**/session-fixture',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><div id="root"></div><script>'+bundle.replaceAll('</script','<\\/script')+'</script>'}));await page.goto('/session-fixture');});
test('session chart uses actual chronological samples and clears on disconnect',async({page})=>{
 await expect(page.getByText('Awaiting a voice response')).toBeVisible();
 await page.waitForFunction(()=>!!(window as unknown as {release?:()=>void}).release);
 await page.evaluate(()=>(window as unknown as {release:()=>void}).release());
 await expect(page.getByText('4 samples')).toBeVisible();
 await expect(page.locator('.session-statistics')).toContainText('1.1 s');
 await expect(page.locator('.session-statistics')).toContainText('1.4 s');
 await expect(page.locator('circle')).toHaveCount(4);
 await page.getByRole('button',{name:'Disconnect fixture'}).click();
 await expect(page.getByText('0 samples')).toBeVisible();
 await expect(page.locator('circle')).toHaveCount(0);
});
test('late diagnostic RPC cannot repopulate a disconnected session',async({page})=>{
 await page.waitForFunction(()=>!!(window as unknown as {release?:()=>void}).release);
 await page.getByRole('button',{name:'Disconnect fixture'}).click();
 await page.evaluate(()=>(window as unknown as {release:()=>void}).release());
 await expect(page.getByText('Connect to see timings')).toBeVisible();
 await expect(page.getByText('0 samples')).toBeVisible();
 await expect(page.locator('circle')).toHaveCount(0);
 expect(await page.evaluate(()=>(window as unknown as {calls:number}).calls)).toBe(1);
});
