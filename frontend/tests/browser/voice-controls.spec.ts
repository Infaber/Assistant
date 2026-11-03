import {test,expect} from '@playwright/test';
import {build} from 'esbuild';
import path from 'node:path';
let bundle: string;
test.beforeAll(async () => {
  const output = await build({entryPoints:[path.resolve('tests/fixtures/voice-controls.tsx')],bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic'});
  bundle = output.outputFiles[0].text;
});
test.beforeEach(async ({page}) => {
  await page.route('**/voice-fixture*',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><div id="root"></div><script>'+bundle.replaceAll('</script','<\\/script')+'</script>'}));
  await page.goto('/voice-fixture');
});
test('isolated voice UI keeps active settings while saving and explicitly resets the override',async ({page})=>{
  await expect(page.getByText('Active voice: Sulafat',{exact:true})).toBeVisible();
  await expect(page.getByLabel('Gemini voice',{exact:true})).toHaveValue('Leda');
  await expect(page.getByText(/Saved changes awaiting a new connection/)).toBeVisible();
  await page.getByLabel('Gemini voice',{exact:true}).selectOption('');
  await page.getByLabel('Conversation warmth').selectOption('high');
  await page.getByRole('button',{name:'Save for next connection'}).click();
  await expect(page.getByText(/Saved\. End and reconnect/)).toBeVisible();
  await expect(page.getByText('Active voice: Sulafat',{exact:true})).toBeVisible();
  await expect(page.locator('.effective-settings')).toContainText('warmth: balanced');
  const requests = await page.evaluate(()=>(window as unknown as {voiceCalls:Record<string,unknown>[]}).voiceCalls);
  expect(requests.map(r=>r.action)).toEqual(['status','save','status']);
  expect(requests[1].reset).toEqual(['google_voice']);
  expect(requests[1].values).toMatchObject({warmth:'high'});
  expect(requests[1].values).not.toHaveProperty('google_voice');
});
test('A/B loading never generates speech and selected samples require a click',async ({page})=>{
  await page.getByText('Compare configurations',{exact:true}).click();
  await page.getByRole('button',{name:'Save A',exact:true}).click();
  await page.getByLabel('Gemini voice',{exact:true}).selectOption('Sulafat');
  await page.getByRole('button',{name:'Load A',exact:true}).click();
  await expect(page.getByLabel('Gemini voice',{exact:true})).toHaveValue('Leda');
  expect(await page.evaluate(()=>(window as unknown as {voiceCalls:unknown[]}).voiceCalls.length)).toBe(1);
  await page.getByLabel('Evaluation sample').selectOption('serious');
  await expect(page.getByText('Serious sample',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Play current voice sample'}).click();
  expect(await page.evaluate(()=>(window as unknown as {voiceCalls:Record<string,unknown>[]}).voiceCalls.at(-1))).toMatchObject({action:'sample',sample:'serious'});
});
test('numerical diagnostics show median and p95 without triggering speech',async ({page})=>{
  await page.getByText('Numerical diagnostics',{exact:true}).click();
  await page.getByRole('button',{name:'Refresh timings'}).click();
  await expect(page.getByRole('table')).toContainText('400');
  await expect(page.getByRole('table')).toContainText('900');
  expect(await page.evaluate(()=>(window as unknown as {voiceCalls:Record<string,unknown>[]}).voiceCalls.map(r=>r.action))).toEqual(['status','status']);
});

test('late save responses cannot replace the disconnected settings state',async ({page})=>{
  await expect(page.getByLabel('Gemini voice',{exact:true})).toHaveValue('Leda');
  await page.evaluate(()=>Object.assign(window,{holdSave:true}));
  await page.getByRole('button',{name:'Save for next connection'}).click();
  await page.waitForFunction(()=>typeof (window as unknown as {releaseSave?:unknown}).releaseSave === 'function');
  await page.evaluate(()=>(window as unknown as {disconnectVoiceFixture:()=>void}).disconnectVoiceFixture());
  await expect(page.getByText('Connect to change voice settings.',{exact:true})).toBeVisible();
  await page.evaluate(()=>(window as unknown as {releaseSave:()=>void}).releaseSave());
  await expect(page.getByLabel('Gemini voice',{exact:true})).toBeDisabled();
  await expect(page.getByText('Connect to change voice settings.',{exact:true})).toBeVisible();
  await expect(page.getByText(/Saved\. End and reconnect/)).toHaveCount(0);
});

for (const reset of [false, true]) {
  test(`saving ${reset ? 'the default reset' : 'identical settings'} clears pending when effective settings match active`,async ({page})=>{
    await page.getByLabel('Gemini voice',{exact:true}).selectOption(reset ? '' : 'Sulafat');
    await page.getByRole('button',{name:'Save for next connection'}).click();
    await expect(page.getByText(/no reconnect is needed/)).toBeVisible();
    await expect(page.locator('.pending-settings')).toHaveCount(0);
    await expect(page.locator('.saved-settings')).toContainText('google voice: Sulafat');
  });
}
test('saving a change then reverting to active settings removes the pending warning',async ({page})=>{
  await page.getByLabel('Gemini voice',{exact:true}).selectOption('Sulafat');
  await page.getByLabel('Conversation warmth').selectOption('high');
  await page.getByRole('button',{name:'Save for next connection'}).click();
  await expect(page.locator('.pending-settings')).toBeVisible();
  await page.getByLabel('Conversation warmth').selectOption('balanced');
  await page.getByRole('button',{name:'Save for next connection'}).click();
  await expect(page.locator('.pending-settings')).toHaveCount(0);
  await expect(page.locator('.effective-settings')).toContainText('warmth: balanced');
});
test('Normal ignores saved Local rate when deciding whether reconnection is needed',async ({page})=>{
  await page.getByLabel('Gemini voice',{exact:true}).selectOption('Sulafat');
  await page.getByLabel('Local speaking rate').selectOption('1.2');
  await page.getByRole('button',{name:'Save for next connection'}).click();
  await expect(page.getByText(/no reconnect is needed/)).toBeVisible();
  await expect(page.locator('.pending-settings')).toHaveCount(0);
});
test('Local ignores Gemini voice but detects saved Local rate changes',async ({page})=>{
  await page.goto('/voice-fixture?mode=local');
  await expect(page.getByText('Active voice: af_heart',{exact:true})).toBeVisible();
  await expect(page.locator('.pending-settings')).toHaveCount(0);
  await page.getByRole('button',{name:'Save for next connection'}).click();
  await expect(page.getByText(/no reconnect is needed/)).toBeVisible();
  await page.getByLabel('Local speaking rate').selectOption('1.2');
  await page.getByRole('button',{name:'Save for next connection'}).click();
  await expect(page.locator('.pending-settings')).toBeVisible();
});

 test('late effective-state refresh cannot overwrite a disconnected session',async ({page})=>{
  await expect(page.getByLabel('Gemini voice',{exact:true})).toHaveValue('Leda');
  await page.evaluate(()=>Object.assign(window,{holdStatus:true}));
  await page.getByRole('button',{name:'Save for next connection'}).click();
  await page.waitForFunction(()=>typeof (window as unknown as {releaseStatus?:unknown}).releaseStatus === 'function');
  await page.evaluate(()=>(window as unknown as {disconnectVoiceFixture:()=>void}).disconnectVoiceFixture());
  await expect(page.getByText('Connect to change voice settings.',{exact:true})).toBeVisible();
  await page.evaluate(()=>(window as unknown as {releaseStatus:()=>void}).releaseStatus());
  await expect(page.locator('.saved-settings')).toHaveCount(0);
  await expect(page.getByLabel('Gemini voice',{exact:true})).toBeDisabled();
 });
