import { test, expect } from "@playwright/test";

test("real local token route accepts the browser origin", async ({ page }) => {
  await page.goto("/");
  const status = await page.evaluate(
    async () => (await fetch("/api/connection", { method: "POST" })).status,
  );
  expect([201, 401, 503]).toContain(status);
});
test("orb is the main screen, typing reveals input, and mobile fits", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.getByLabel(/^Message (?:Ariana|Jarvis)$/, { exact: true })).toBeHidden();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("aside")).toHaveCount(0);
  await expect
    .poll(() =>
      page
        .locator("canvas")
        .evaluate((canvas) => (canvas as HTMLCanvasElement).width),
    )
    .toBeGreaterThan(300);
  await page.keyboard.press("h");
  await expect(page.getByLabel(/^Message (?:Ariana|Jarvis)$/, { exact: true })).toHaveValue(
    "h",
  );
  await expect(
    page.getByLabel(/^Message (?:Ariana|Jarvis)$/, { exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByLabel(/^Message (?:Ariana|Jarvis)$/, { exact: true })).toBeHidden();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
test("six styles and caption/feedback preferences persist without connecting", async ({
  page,
}) => {
  let requests = 0;
  await page.route("**/api/connection", async (route) => {
    requests++;
    await route.fulfill({ status: 503, json: { error: "Unavailable" } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  for (const [index, name] of [
    "Flowing mesh",
    "Glass bubble",
    "Crystal burst",
    "Shard vortex",
    "Wireframe globe",
    "Particle swirl",
  ].entries()) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.locator("canvas")).toHaveAttribute(
      "data-style",
      String(index),
    );
    await expect(
      page.getByRole("button", { name, exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
  }
  await page.getByLabel("Captions", { exact: true }).check();
  await page.getByLabel("Spoken feedback during tools").uncheck();
  await page.reload();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByLabel("Captions", { exact: true })).toBeChecked();
  await expect(page.getByLabel("Spoken feedback during tools")).not.toBeChecked();
  await expect(page.locator("canvas")).toHaveAttribute("data-style", "5");
  expect(requests).toBe(0);
});
test("explicit start sends access code, errors stay visible and retry works", async ({
  page,
}) => {
  const headers: string[] = [];
  await page.route("**/api/connection", async (route) => {
    headers.push(route.request().headers().authorization);
    await route.fulfill({
      status: 503,
      json: { error: "Add your LiveKit credentials" },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByLabel("Access code", { exact: true })
    .fill("workspace-secret");
  await page.getByRole("button", { name: "Save settings" }).click();
  expect(headers).toEqual([]);
  await page.locator(".orb-touch").click();
  await expect(page.locator(".error-banner[role=alert]")).toContainText(
    "Add your LiveKit credentials",
  );
  expect(headers).toEqual(["Bearer workspace-secret"]);
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect.poll(() => headers.length).toBe(2);
});
test("cancels an in-flight connection without an error", async ({ page }) => {
  let releaseRequest!: () => void;
  const pendingRequest = new Promise<void>((resolve) => {
    releaseRequest = resolve;
  });
  let requestStarted = false;
  await page.route("**/api/connection", async (route) => {
    requestStarted = true;
    await pendingRequest;
    await route
      .fulfill({ status: 503, json: { error: "Should not appear" } })
      .catch(() => {});
  });
  try {
    await page.goto("/");
    await page.locator(".orb-touch").click();
    await expect.poll(() => requestStarted).toBe(true);
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("button", { name: "Cancel connection" }).click();
    // Let the intercepted request settle after cancellation; routed WebKit
    // requests do not always observe AbortSignal until the route is released.
    releaseRequest();
    await expect(page.locator(".orb-touch")).toBeEnabled();
    await expect(page.locator(".error-banner[role=alert]")).toHaveCount(0);
  } finally {
    releaseRequest();
  }
});
test("global pasted pictures reveal composer, stage files and remove previews", async ({
  page,
}) => {
  await page.goto("/");
  await page.evaluate(() => {
    const transfer = new DataTransfer();
    transfer.items.add(
      new File([new Uint8Array([137, 80, 78, 71])], "pasted.png", {
        type: "image/png",
      }),
    );
    document.body.dispatchEvent(
      new ClipboardEvent("paste", { bubbles: true, clipboardData: transfer }),
    );
  });
  await expect(
    page.getByRole("img", { name: "Preview of pasted.png" }),
  ).toBeVisible();
  await page.getByLabel("Choose attachments").setInputFiles({
    name: "lab.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Robotics Friday"),
  });
  await expect(page.getByLabel("Attachments ready to send")).toContainText(
    "lab.txt",
  );
  await expect(
    page.getByRole("button", { name: "Send message", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Remove lab.txt" }).click();
  await expect(page.getByLabel("Attachments ready to send")).not.toContainText(
    "lab.txt",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("unsupported attachments report errors and check-ins stay in settings", async ({
  page,
}) => {
  await page.goto("/");
  await page.keyboard.press("Control+k");
  await page.getByLabel("Choose attachments").setInputFiles({
    name: "archive.zip",
    mimeType: "application/zip",
    buffer: Buffer.from("binary"),
  });
  await expect(page.locator(".error-banner[role=alert]")).toContainText(
    "use a picture",
  );
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("switch", { name: /^Let (?:Ariana|Jarvis) start conversations$/ }),
  ).toBeDisabled();
  await expect(
    page.getByRole("switch", { name: /^Let (?:Ariana|Jarvis) start conversations$/ }),
  ).toHaveAttribute("aria-checked", "false");
});
test("native companion auto-connects without opening the microphone", async ({
  page,
}) => {
  const authorizations: string[] = [];
  await page.addInitScript(() => {
    window.arianaDesktop = { desktop: true, accessCode: "native-test-code" };
  });
  await page.route("**/api/connection", async (route) => {
    authorizations.push(route.request().headers().authorization);
    await route.fulfill({
      status: 503,
      json: { error: "Mock native connection unavailable" },
    });
  });
  await page.goto("/");
  await expect(page.locator(".error-banner[role=alert]")).toContainText(
    "Mock native connection unavailable",
  );
  expect(authorizations).toEqual(["Bearer native-test-code"]);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Proactive check-ins" }),
  ).toContainText("Close the window");
  await expect(
    page.getByRole("switch", { name: /^Let (?:Ariana|Jarvis) start conversations$/ }),
  ).toHaveAttribute("aria-checked", "false");
});
test("reduced motion produces a stable orb and voice cues decode", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.waitForTimeout(500);
  const first = await page.locator("canvas").screenshot();
  await page.waitForTimeout(200);
  expect(await page.locator("canvas").screenshot()).toEqual(first);
  const clips = await page.evaluate(async () => {
    const ac = new AudioContext();
    try {
      return await Promise.all(
        ["thinking", "moment", "still-here"].map(async (name) => {
          const data = await (await fetch(`/audio/${name}.wav`)).arrayBuffer();
          const decoded = await ac.decodeAudioData(data);
          return {
            duration: decoded.duration,
            peak: decoded
              .getChannelData(0)
              .reduce((peak, value) => Math.max(peak, Math.abs(value)), 0),
          };
        }),
      );
    } finally {
      await ac.close();
    }
  });
  for (const clip of clips) {
    expect(clip.duration).toBeGreaterThan(0.2);
    expect(clip.duration).toBeLessThan(8);
    expect(clip.peak).toBeGreaterThan(0.01);
  }
});

test("keyboard can activate the orb without the typing shortcut stealing Enter", async ({
  page,
}) => {
  let requests = 0;
  await page.route("**/api/connection", async (route) => {
    requests++;
    await route.fulfill({
      status: 503,
      json: { error: "Keyboard connection test" },
    });
  });
  await page.goto("/");
  // A canvas defaults to width 300 before React hydrates. The desktop orb
  // measures 340 CSS pixels; wait for its effect to resize it before assigning
  // programmatic focus, which WebKit can otherwise lose during the first mount.
  await expect.poll(() => page.locator("canvas").evaluate(canvas => (canvas as HTMLCanvasElement).width)).toBeGreaterThan(300);
  await page.locator(".orb-touch").focus();
  await expect(page.locator(".orb-touch")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator(".error-banner")).toContainText(
    "Keyboard connection test",
  );
  expect(requests).toBe(1);
});

test("native pause survives sleep/network recovery and repeated wakes join once", async ({
  page,
}) => {
  let requests = 0;
  await page.addInitScript(() => {
    window.arianaDesktop = { desktop: true, accessCode: "native-test" };
  });
  await page.route("**/api/connection", async (route) => {
    requests++;
    await new Promise((resolve) => setTimeout(resolve, 200));
    await route
      .fulfill({ status: 503, json: { error: "Network unavailable" } })
      .catch(() => {});
  });
  await page.goto("/");
  await expect.poll(() => requests).toBe(1);
  await page.evaluate(() => {
    window.dispatchEvent(new Event("ariana:pause"));
    window.dispatchEvent(new Event("ariana:sleep"));
    window.dispatchEvent(new Event("ariana:service-recover"));
  });
  await page.waitForTimeout(2500);
  expect(requests).toBe(1);
  await page.reload();
  await page.waitForTimeout(700);
  expect(requests).toBe(1);
  await page.evaluate(() => {
    window.dispatchEvent(new Event("ariana:wake-word"));
    window.dispatchEvent(new Event("ariana:wake-word"));
    window.dispatchEvent(new Event("ariana:wake-word"));
  });
  await expect.poll(() => requests).toBe(2);
  await page.evaluate(() => window.dispatchEvent(new Event("ariana:pause")));
});

test("native auth failure waits for explicit reconnect", async ({ page }) => {
  let requests = 0;
  await page.addInitScript(() => {
    window.arianaDesktop = { desktop: true, accessCode: "native-test" };
  });
  await page.route("**/api/connection", async (route) => {
    requests++;
    await route.fulfill({
      status: 401,
      json: { error: "Enter the correct access code" },
    });
  });
  await page.goto("/");
  await expect.poll(() => requests).toBe(1);
  await page.waitForTimeout(2500);
  expect(requests).toBe(1);
});

test('local selection remains selected, not active, when backend startup fails', async ({page}) => {
  let requested='';
  await page.route('**/api/connection',async route=>{
    requested=JSON.parse(route.request().postData() || '{}').mode;
    await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Local model unavailable. Start Ollama.'})});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Unrestricted',exact:true}).click();
  await expect(page.getByRole('button',{name:'Unrestricted',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('canvas.ariana-orb')).toHaveAttribute('data-mode','normal');
  expect(await page.evaluate(()=>localStorage.getItem('ariana-ai-mode'))).toBeNull();
  await page.getByRole('button',{name:'Start conversation',exact:true}).first().click();
  await expect(page.getByText('Local model unavailable. Start Ollama.',{exact:true})).toBeVisible();
  expect(requested).toBe('local');
  await expect(page.locator('canvas.ariana-orb')).toHaveAttribute('data-mode','normal');
  await page.getByRole('button',{name:'Normal',exact:true}).click();
  await expect(page.getByRole('button',{name:'Normal',exact:true})).toHaveAttribute('aria-pressed','true');
});

test("conversation transfer requires a fresh opt-in for each engine switch", async ({ page }) => {
  await page.goto("/");
  const transfer = page.getByLabel("Keep recent conversation for the next switch");
  await expect(transfer).not.toBeChecked();
  await transfer.check();
  await page.getByRole("button", { name: "Unrestricted", exact: true }).click();
  await expect(transfer).not.toBeChecked();
  await page.reload();
  await expect(transfer).not.toBeChecked();
});

test("native proactive priority filter persists without enabling extra actions", async ({ page }) => {
  await page.addInitScript(() => {
    window.arianaDesktop = { desktop: true, accessCode: "fixture-code" };
    localStorage.setItem("ariana.desktop.check-ins", JSON.stringify({enabled: true, interval: 15, quietStart: 22, quietEnd: 8, minimumImportance: 4}));
  });
  await page.route("**/api/connection", route => route.fulfill({status: 503, json: {error: "Fixture offline"}}));
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const priority = page.getByLabel("Minimum follow-up priority");
  await expect(priority).toHaveValue("4");
  await priority.selectOption("5");
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("ariana.desktop.check-ins") || "{}").minimumImportance)).toBe(5);
  await expect(page.getByRole("switch", { name: /^Let (?:Ariana|Jarvis) start conversations$/ })).toBeDisabled();
});

test('voice settings open silently and visual listening cues can be disabled', async ({page}) => {
  let connections=0;
  await page.route('**/api/connection',route=>{connections++;return route.fulfill({status:503,json:{error:'Fixture offline'}});});
  await page.addInitScript(()=>{(window as unknown as {plays:number}).plays=0;HTMLMediaElement.prototype.play=function(){(window as unknown as {plays:number}).plays++;return Promise.resolve();};});
  await page.goto('/');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await expect(page.getByLabel('Gemini voice',{exact:true})).toBeDisabled();
  await page.getByText('Compare configurations',{exact:true}).click();
  await expect(page.getByRole('button',{name:'Play current voice sample'})).toBeDisabled();
  await page.getByLabel('Listening cue level').selectOption('off');
  expect(await page.evaluate(()=>localStorage.getItem('ariana.listening-cues'))).toBe('off');
  expect(await page.evaluate(()=>(window as unknown as {plays:number}).plays)).toBe(0);
  expect(connections).toBe(0);
  await page.reload();
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await expect(page.getByLabel('Listening cue level')).toHaveValue('off');
});

test('native wake settings send bounded explicit configuration requests', async ({page}) => {
  await page.addInitScript(()=>{
    const calls:unknown[]=[];
    (window as unknown as {wakeCalls:unknown[]}).wakeCalls=calls;
    window.arianaDesktop={desktop:true,accessCode:'fixture-only',postMessage:(message)=>{
      calls.push(message);
      if(message.type==='wake-settings' && message.enabled!==undefined)window.dispatchEvent(new CustomEvent('ariana:wake-status',{detail:{enabled:message.enabled,ready:message.enabled,phrase:'Ariana',configuring:false,error:''}}));
      if(message.type==='wake-status')window.dispatchEvent(new CustomEvent('ariana:wake-status',{detail:{enabled:false,ready:false,phrase:'Hey Ariana',configuring:false,error:''}}));
    }};
  });
  await page.route('**/api/connection',route=>route.fulfill({status:503,json:{error:'Fixture offline'}}));
  await page.goto('/');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await expect(page.getByLabel('Wake phrase',{exact:true})).toHaveValue('Hey Ariana');
  await page.getByLabel('Wake phrase',{exact:true}).selectOption('Ariana');
  await page.getByRole('button',{name:'Configure local phrase'}).click();
  expect(await page.evaluate(()=>(window as unknown as {wakeCalls:unknown[]}).wakeCalls)).toContainEqual({type:'wake-settings',phrase:'Ariana'});
  await page.getByLabel('Local wake detection',{exact:true}).check();
  expect(await page.evaluate(()=>(window as unknown as {wakeCalls:unknown[]}).wakeCalls)).toContainEqual({type:'wake-settings',enabled:true});
});


test("conversation state and microphone distinction are visible without connecting", async ({page}) => {
  let connections = 0;
  await page.route("**/api/connection", route => { connections++; return route.fulfill({status:503,json:{error:"offline fixture"}}); });
  await page.goto("/");
  await expect(page.getByRole("heading", {name:"Standby",exact:true})).toBeVisible();
  await expect(page.getByText("Conversation microphone is off.", {exact:false})).toBeVisible();
  await expect(page.getByRole("region", {name:"Recent conversation"})).toBeVisible();
  await page.getByRole("button", {name:"Settings",exact:true}).click();
  await expect(page.getByRole("heading", {name:"Wake & microphone"})).toBeVisible();
  await expect(page.getByLabel("Local speaking rate")).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", {name:"Settings",exact:true})).toBeFocused();
  expect(connections).toBe(0);
});

test("mobile companion remains within viewport with reduced motion", async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.goto("/");
  await expect(page.getByRole("heading",{name:"Standby",exact:true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button",{name:"Settings",exact:true}).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const bounds = await dialog.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
});

test('long errors remain scrollable above controls on short mobile screens', async ({page})=>{
  await page.setViewportSize({width:390,height:568});
  await page.route('**/api/connection',route=>route.fulfill({status:403,json:{error:'Microphone permission denied. Review microphone access in System Settings. '+ 'Connection details '.repeat(60)}}));
  await page.goto('/');
  await page.getByRole('button',{name:'Start conversation',exact:true}).first().click();
  await expect(page.getByRole('heading',{name:'Microphone denied',exact:true})).toBeVisible();
  const error=await page.locator('.error-banner').boundingBox();
  const controls=await page.locator('.ai-mode-control').boundingBox();
  expect(error!.y).toBeGreaterThan(130);
  expect(error!.y+error!.height).toBeLessThan(controls!.y);
  expect(await page.locator('.error-banner p').evaluate(el=>el.scrollHeight>el.clientHeight)).toBe(true);
  await expect(page.getByRole('button',{name:'Retry',exact:true})).toBeVisible();
  await page.getByLabel('Error details').focus();
  await page.keyboard.press('End');
  await expect.poll(()=>page.locator('.error-banner p').evaluate(el=>el.scrollTop)).toBeGreaterThan(0);
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  const dialog=await page.getByRole('dialog').boundingBox();
  expect(dialog!.y).toBeGreaterThanOrEqual(0);
  expect(dialog!.y+dialog!.height).toBeLessThanOrEqual(568);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'Settings',exact:true})).toBeFocused();
});


test('synthetic long transcript stays separate from orb and controls',async ({page})=>{
  for (const height of [844,568]) {
    await page.setViewportSize({width:390,height});
    await page.goto('/');
    // A working interaction proves hydration finished before DOM-only stress content.
    await page.getByRole('button',{name:'Settings',exact:true}).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).not.toBeVisible();
    await page.locator('.conversation-preview').evaluate(el=>{
      const article=document.createElement('article');
      const p=document.createElement('p');
      p.textContent='Synthetic layout content only. '+ 'Long-message-without-breaks'.repeat(100);
      article.append(p);el.replaceChildren(article);
    });
    const preview=await page.locator('.conversation-preview').boundingBox();
    const controls=await page.locator('.ai-mode-control').boundingBox();
    expect(preview!.y+preview!.height).toBeLessThan(controls!.y);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    if(height>650){const orb=await page.locator('.orb-touch').boundingBox();expect(orb!.y+orb!.height).toBeLessThan(preview!.y);}
    else await expect(page.locator('.orb-center')).toBeVisible();
  }
});

test('workspace navigation and message entry remain silent and keyboard accessible',async ({page})=>{
  let connections=0;
  await page.route('**/api/connection',route=>{connections++;return route.fulfill({status:503,json:{error:'Offline fixture'}});});
  await page.goto('/');
  await page.getByRole('button',{name:'Preferences',exact:true}).click();
  await page.getByRole('navigation',{name:'Settings sections'}).getByRole('button',{name:'Appearance',exact:true}).click();
  await expect(page.getByRole('button',{name:'Glass bubble',exact:true})).toBeInViewport();
  await page.keyboard.press('Escape');
  await page.getByRole('navigation',{name:'Workspace'}).getByRole('button',{name:/Conversation/}).click();
  await expect(page.getByRole('heading',{name:'Conversation',exact:true}).last()).toBeVisible();
  await page.getByRole('button',{name:'Close conversation',exact:true}).click();
  await page.getByRole('button',{name:/What's on your mind/}).click();
  await expect(page.getByLabel(/^Message (?:Ariana|Jarvis)$/, {exact:true})).toBeFocused();
  await page.keyboard.press('Escape');
  expect(connections).toBe(0);
});

test('workspace panels fit desktop, tablet and narrow mobile without overlap',async ({page})=>{
  for(const viewport of [{width:1440,height:900},{width:1024,height:768},{width:768,height:1024},{width:320,height:568}]){
    await page.setViewportSize(viewport);await page.goto('/');
    await expect(page.getByRole('heading',{name:'Standby',exact:true})).toBeVisible();
    const voice=await page.locator('.voice-space').boundingBox();
    const conversation=await page.locator('.conversation-preview').boundingBox();
    if(viewport.width>600) expect(voice!.x+voice!.width).toBeLessThan(conversation!.x);
    else expect(voice!.y+voice!.height).toBeLessThan(conversation!.y);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    if(viewport.width>900){const nav=await page.locator('.workspace-nav>button').last().boundingBox();const engine=await page.locator('.ai-mode-control').boundingBox();expect(nav!.y+nav!.height).toBeLessThan(engine!.y);}
  }
});
