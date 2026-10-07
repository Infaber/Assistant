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
  await expect(page.getByLabel("Message Ariana", { exact: true })).toBeHidden();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("aside")).toHaveCount(0);
  await expect
    .poll(() =>
      page
        .locator("canvas")
        .evaluate((canvas) => (canvas as HTMLCanvasElement).width),
    )
    .toBeGreaterThan(400);
  await page.keyboard.press("h");
  await expect(page.getByLabel("Message Ariana", { exact: true })).toHaveValue(
    "h",
  );
  await expect(
    page.getByLabel("Message Ariana", { exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Message Ariana", { exact: true })).toBeHidden();
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
  await page.getByLabel("Spoken thinking feedback").uncheck();
  await page.reload();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByLabel("Captions", { exact: true })).toBeChecked();
  await expect(page.getByLabel("Spoken thinking feedback")).not.toBeChecked();
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
    page.getByRole("switch", { name: "Let Ariana start conversations" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("switch", { name: "Let Ariana start conversations" }),
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
    page.getByRole("switch", { name: "Let Ariana start conversations" }),
  ).toHaveAttribute("aria-checked", "true");
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
  await page.locator(".orb-touch").focus();
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
