import { expect, test, type Page } from "@playwright/test";

const STEPS = [1, 2, 3, 2, 3, 3, 2, 2];
const TOTAL = STEPS.reduce((a, b) => a + b, 0);
const go = async (page: Page, slide: number, step = 1) => {
  await page.goto(`/#/${slide}/${step}`);
  await page.reload();
  await expect(page.locator(".slide-layer")).toHaveCount(1);
};
const announce = (page: Page) => page.getByTestId("announce");

test.describe("navigation engine", () => {
  test("keyboard: arrows, space, shift+arrows, numbers, home/end, restart", async ({ page }) => {
    await page.goto("/");
    await expect(announce(page)).toContainText("Слайд 1 из 8");
    await page.keyboard.press("ArrowRight"); // slide 1 has one state
    await expect(page).toHaveURL(/#\/2\/1$/);
    await page.keyboard.press("Space");
    await expect(page).toHaveURL(/#\/2\/2$/);
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(/#\/3\/1$/);
    await page.keyboard.press("ArrowLeft"); // back lands on the finished state of slide 2
    await expect(page).toHaveURL(/#\/2\/2$/);
    await page.keyboard.press("Shift+ArrowRight");
    await expect(page).toHaveURL(/#\/3\/1$/);
    await page.keyboard.press("4");
    await expect(announce(page)).toContainText("Слайд 4 из 8");
    await page.keyboard.press("End");
    await expect(page).toHaveURL(/#\/8\/1$/);
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(/#\/8\/2$/);
    await page.keyboard.press("ArrowRight"); // no-op at the end
    await expect(page).toHaveURL(/#\/8\/2$/);
    await page.keyboard.press("Home");
    await expect(page).toHaveURL(/#\/1\/1$/);
    await page.keyboard.press("5");
    await page.keyboard.press("r");
    await expect(page).toHaveURL(/#\/1\/1$/);
  });

  test("deep links restore exact state and the hash follows navigation", async ({ page }) => {
    await go(page, 6, 2);
    await expect(announce(page)).toContainText("Слайд 6 из 8");
    await expect(announce(page)).toContainText("Шаг 2 из 3");
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(/#\/6\/3$/);
  });

  test("overview dialog: quick navigation, Escape, focus restore", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Обзор слайдов/ }).focus();
    await page.keyboard.press("Enter");
    const dlg = page.getByRole("dialog", { name: "Обзор слайдов" });
    await expect(dlg).toBeVisible();
    await expect(dlg.locator(".ov-card")).toHaveCount(8);
    await page.keyboard.press("Escape");
    await expect(dlg).toBeHidden();
    await expect(page.getByRole("button", { name: /Обзор слайдов/ })).toBeFocused();
    await page.keyboard.press("o");
    await dlg.locator(".ov-card").nth(4).click();
    await expect(dlg).toBeHidden();
    await expect(announce(page)).toContainText("Слайд 5 из 8");
  });

  test("progress segments jump to slides", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Слайд 3: /, includeHidden: false }).click();
    await expect(announce(page)).toContainText("Слайд 3 из 8");
  });

  test("presenter notes show the current step, a timer and the next slide", async ({ page }) => {
    await go(page, 3, 2);
    await page.keyboard.press("n");
    const notes = page.getByRole("complementary", { name: "Заметки докладчика" });
    await expect(notes).toBeVisible();
    await expect(notes.locator("li.on")).toContainText("Дальше — то, чего нет у правил");
    await expect(notes).toContainText("От перевода до решения");
    await notes.getByRole("button", { name: "Запустить таймер" }).click();
    await expect(notes.getByRole("button", { name: "Пауза таймера" })).toBeVisible();
    await expect(notes.locator(".t")).toContainText("/ 3:00");
    await page.keyboard.press("n");
    await expect(notes).toBeHidden();
  });

  test("help lists shortcuts and closes with Escape", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Горячие клавиши/ }).click();
    await expect(page.getByRole("dialog", { name: "Горячие клавиши" })).toContainText("Пробел");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  });

  test("touch swipe navigates", async ({ page }) => {
    await page.goto("/");
    const swipe = (from: number, to: number) =>
      page.getByTestId("stage").evaluate((el, [a, b]) => {
        const fire = (type: string, x: number) => el.dispatchEvent(new PointerEvent(type, { pointerType: "touch", clientX: x, clientY: 300, bubbles: true }));
        fire("pointerdown", a);
        fire("pointerup", b);
      }, [from, to]);
    await swipe(900, 400);
    await expect(page).toHaveURL(/#\/2\/1$/);
    await swipe(400, 900);
    await expect(page).toHaveURL(/#\/1\/1$/);
  });

  test("fullscreen control is present and honest about support", async ({ page }) => {
    await page.goto("/");
    const fs = page.getByRole("button", { name: /Полный экран/ });
    await expect(fs).toBeVisible();
    const supported = await page.evaluate(() => document.fullscreenEnabled);
    if (supported) await expect(fs).toBeEnabled();
    else await expect(fs).toBeDisabled();
  });
});

test.describe("slide content", () => {
  test("every slide states one idea as its h2", async ({ page }) => {
    const heads = [
      "Находим не подозрительные переводы, а мошеннические схемы целиком",
      "Правило видит счёт и не отличает схему от бизнеса",
      "Форма сети — лишь повод. Решают время и контекст",
      "От перевода до решения — шесть проверяемых этапов",
      "Аналитик получает не алерт, а дело с доказательствами",
      "Очередь в 4,5 раза короче, ложных тревог — вдвое меньше",
      "Банк получает короткую очередь и дело, готовое к аудиту",
      "Первый шаг пилота — офлайн-реплей на истории банка",
    ];
    for (let i = 0; i < heads.length; i++) {
      await go(page, i + 1, 1);
      await expect(page.locator(".slide-layer h2")).toContainText(heads[i]);
    }
  });

  test("02: two identical alerts, then the networks behind them", async ({ page }) => {
    await go(page, 2, 1);
    const slide = page.locator(".slide-layer");
    await expect(slide.getByText("Правило «веерный приток»: 5 отправителей за 3 дня")).toHaveCount(2);
    await expect(slide.locator(".s2-truth").first()).toHaveAttribute("aria-hidden", "true");
    await page.keyboard.press("ArrowRight");
    await expect(slide.locator(".s2-truth").first()).toHaveAttribute("aria-hidden", "false");
    await expect(slide.getByText("Воронка сбора", { exact: true })).toBeVisible();
    await expect(slide.getByText("Расчёты с мерчантом", { exact: true })).toBeVisible();
  });

  test("03: the three tests appear one per step, with product figures", async ({ page }) => {
    await go(page, 3, 1);
    const slide = page.locator(".slide-layer");
    await expect(slide.getByRole("heading", { name: "Структура" })).toBeVisible();
    await expect(slide.locator(".s3-tests > li").nth(1)).toHaveAttribute("aria-hidden", "true");
    await page.keyboard.press("ArrowRight");
    await expect(slide.getByRole("heading", { name: "Хронология" })).toBeVisible();
    await expect(slide).toContainText("81,9 %");
    await page.keyboard.press("ArrowRight");
    await expect(slide.getByRole("heading", { name: "Похожие счета" })).toBeVisible();
    await expect(slide).toContainText("приоритет 55 из 100");
    await expect(slide).toContainText("не вероятность мошенничества");
  });

  test("04: six real pipeline stages, the stack, then what already works", async ({ page }) => {
    await go(page, 4, 1);
    const slide = page.locator(".slide-layer");
    await expect(slide.getByRole("list", { name: "Этапы обработки" }).getByRole("listitem")).toHaveCount(6);
    await expect(slide.locator(".s4-works")).toHaveAttribute("aria-hidden", "true");
    for (const t of ["Python", "FastAPI", "NetworkX", "PostgreSQL", "SQLAlchemy", "Alembic", "React", "TypeScript", "Vite", "Cytoscape.js", "Docker", "Pytest", "Playwright"]) {
      await expect(slide.getByRole("list", { name: "Технологии" })).toContainText(t);
    }
    await page.keyboard.press("ArrowRight");
    await expect(slide.locator(".s4-stack")).toHaveAttribute("aria-hidden", "true");
    await expect(slide.getByRole("heading", { name: "Живое демо" })).toBeVisible();
    await expect(slide.getByRole("heading", { name: "Тесты и CI" })).toBeVisible();
  });

  test("05: real screenshots at native size, tabs switch views", async ({ page }) => {
    await go(page, 5, 1);
    const imgs = page.locator(".s5-frame img");
    await expect(imgs).toHaveCount(2);
    for (const i of [0, 1]) {
      const ok = await imgs.nth(i).evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth === 1440);
      expect(ok).toBe(true);
      // never upscaled: rendered width ≤ natural width in canvas px
      const w = await imgs.nth(i).evaluate((el: HTMLImageElement) => el.offsetWidth);
      expect(w).toBeLessThanOrEqual(1440);
    }
    await page.getByRole("button", { name: "Решение" }).click();
    await expect(page).toHaveURL(/#\/5\/3$/);
    await expect(page.locator(".slide-layer")).toContainText("Журнал аудита только на добавление");
    await page.getByRole("button", { name: "Очередь" }).click();
    await expect(page).toHaveURL(/#\/5\/1$/);
  });

  test("06: queue, false alarms, then what was found — numbers from the artifact, scope always on", async ({ page }) => {
    await go(page, 6, 1);
    const slide = page.locator(".slide-layer");
    for (const v of ["42,6", "9,5"]) await expect(slide).toContainText(v);
    await expect(slide.locator("[data-row=legit]")).toHaveAttribute("aria-hidden", "true");
    await expect(slide).toContainText("Синтетические данные");
    await page.keyboard.press("ArrowRight");
    for (const v of ["80,5 %", "37,5 %", "103 из 128", "48 из 128"]) await expect(slide.locator("[data-row=legit]")).toContainText(v);
    await expect(slide.locator(".s6-found")).toHaveAttribute("aria-hidden", "true");
    await page.keyboard.press("ArrowRight");
    const found = slide.locator(".s6-found");
    await expect(found).toContainText("73 из 92");
    await expect(found).toHaveAttribute("aria-hidden", "false");
    await expect(slide.getByRole("region", { name: "Методика" })).toContainText("220");
    // metrics withdrawn after the audit must not appear
    for (const v of ["88,0", "48,3", "32,7", "79,4"]) await expect(slide).not.toContainText(v);
  });

  test("07: value for the bank's three stakeholders, then why a pilot is easy to start", async ({ page }) => {
    await go(page, 7, 1);
    const slide = page.locator(".slide-layer");
    const cards = slide.getByRole("list", { name: "Ценность для банка" }).getByRole("listitem");
    await expect(cards).toHaveCount(3);
    await expect(slide).toContainText("4,5×");
    await expect(slide.getByRole("heading", { name: "Комплаенсу и аудиту" })).toBeVisible();
    await expect(slide.locator(".s7-easy")).toHaveAttribute("aria-hidden", "true");
    await page.keyboard.press("ArrowRight");
    await expect(slide.locator(".s7-easy")).toHaveAttribute("aria-hidden", "false");
    await expect(slide.locator(".s7-easy")).toContainText("CSV");
  });

  test("08: pilot path, the ask, then QR and live links", async ({ page }) => {
    await go(page, 8, 1);
    const slide = page.locator(".slide-layer");
    await expect(slide.getByRole("list", { name: "Этапы пилота" }).getByRole("listitem")).toHaveCount(3);
    await expect(slide).toContainText("Что нужно от банка");
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("img", { name: /QR-код/ })).toBeVisible();
    await expect(page.getByRole("link", { name: "github.com/SaginbekDaniel/SYNAPTIC-LABS" })).toHaveAttribute("href", "https://github.com/SaginbekDaniel/SYNAPTIC-LABS");
    await expect(page.getByRole("link", { name: "web-production-4593b103.up.railway.app" })).toHaveAttribute("href", "https://web-production-4593b103.up.railway.app");
  });
});

test.describe("layout integrity", () => {
  /** Every visible element of every reveal state must sit inside the 80px safe area (canvas coordinates). */
  for (let slide = 1; slide <= STEPS.length; slide++) {
    test(`safe area: slide ${slide}, all ${STEPS[slide - 1]} states`, async ({ page }) => {
      test.setTimeout(90_000);
      await page.setViewportSize({ width: 1920, height: 1080 });
      await go(page, slide, 1);
      for (let step = 1; step <= STEPS[slide - 1]; step++) {
        await page.evaluate((h) => (location.hash = h), `#/${slide}/${step}`);
        await page.waitForTimeout(step === 1 ? 3000 : 1500);
        const bad = await page.evaluate(() => {
          const canvas = document.querySelector(".canvas")!.getBoundingClientRect();
          const scale = canvas.width / 1920;
          const out: string[] = [];
          document.querySelectorAll(".slide-layer *").forEach((el) => {
            if (el.closest(".s5-frame") && !el.classList.contains("s5-frame")) return; // screenshot pans inside its clipped frame
            const cs = getComputedStyle(el);
            if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity) === 0) return;
            if (el.closest("[aria-hidden='true']")) return;
            if (el.children.length > 0 && !(el instanceof SVGElement)) return; // leaves only
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) return;
            const x1 = (r.left - canvas.left) / scale, y1 = (r.top - canvas.top) / scale;
            const x2 = (r.right - canvas.left) / scale, y2 = (r.bottom - canvas.top) / scale;
            if (x1 < 79 || y1 < 79 || x2 > 1841 || y2 > 1001) out.push(`${el.tagName}.${(el as HTMLElement).className?.toString?.().slice(0, 30)} [${Math.round(x1)},${Math.round(y1)} → ${Math.round(x2)},${Math.round(y2)}] "${(el.textContent ?? "").slice(0, 24)}"`);
          });
          return out;
        });
        expect(bad, `slide ${slide} step ${step}`).toEqual([]);
      }
    });
  }

  test("no text smaller than 22 canvas px on any slide state", async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1920, height: 1080 });
    const small: string[] = [];
    for (let slide = 1; slide <= STEPS.length; slide++) for (let step = 1; step <= STEPS[slide - 1]; step++) {
      await go(page, slide, step);
      await page.waitForTimeout(1500);
      const found = await page.evaluate(() => {
        const out: string[] = [];
        document.querySelectorAll(".slide-layer *").forEach((el) => {
          const own = [...el.childNodes].some((n) => n.nodeType === 3 && (n.textContent ?? "").trim().length > 0);
          if (!own) return;
          const fs = parseFloat(getComputedStyle(el).fontSize);
          if (fs < 21.9) out.push(`${fs}px "${(el.textContent ?? "").trim().slice(0, 30)}"`);
        });
        return out;
      });
      small.push(...found.map((f) => `slide ${slide}/${step}: ${f}`));
    }
    expect(small).toEqual([]);
  });

  for (const vp of [{ w: 1440, h: 900 }, { w: 1280, h: 720 }, { w: 844, h: 390 }, { w: 390, h: 844 }]) {
    test(`canvas is fully visible at ${vp.w}x${vp.h}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.w, height: vp.h });
      for (const slide of [1, 3, 5]) {
        await go(page, slide, 1);
        const box = await page.getByTestId("canvas").boundingBox();
        expect(box).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(-1);
        expect(box!.y).toBeGreaterThanOrEqual(-1);
        expect(box!.x + box!.width).toBeLessThanOrEqual(vp.w + 1);
        expect(box!.y + box!.height).toBeLessThanOrEqual(vp.h + 1);
        expect(Math.abs(box!.width / box!.height - 16 / 9)).toBeLessThan(0.01);
      }
      if (vp.h > vp.w) await expect(page.getByRole("status")).toContainText("Поверните устройство");
    });
  }
});

test.describe("accessibility and safety", () => {
  test("reduced motion stops all looping CSS animations", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await go(page, 1, 3);
    await page.waitForTimeout(1500);
    const running = await page.evaluate(() => document.getAnimations().filter((a) => a instanceof CSSAnimation).map((a) => (a as CSSAnimation).animationName));
    expect(running).toEqual([]);
    await go(page, 4, 1);
    await page.waitForTimeout(1500);
    const running6 = await page.evaluate(() => document.getAnimations().filter((a) => a instanceof CSSAnimation).map((a) => (a as CSSAnimation).animationName));
    expect(running6).toEqual([]);
  });

  test("no console errors and no third-party requests on any slide", async ({ page, baseURL }) => {
    const errors: string[] = [];
    const external: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("request", (r) => {
      if (!r.url().startsWith(baseURL!) && !r.url().startsWith("data:")) external.push(r.url());
    });
    await page.goto("/");
    for (let i = 0; i < TOTAL; i++) {
      await page.keyboard.press("ArrowRight");
      await page.waitForTimeout(120);
    }
    expect(errors).toEqual([]);
    expect(external).toEqual([]);
  });

  test("every control has an accessible name and the page has one h1", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1")).toHaveCount(1);
    const unnamed = await page.evaluate(() =>
      [...document.querySelectorAll("button, a")].filter((b) => !(b.getAttribute("aria-label") || b.textContent?.trim())).length,
    );
    expect(unnamed).toBe(0);
  });

  test("the deck never claims a bank integration or production readiness", async ({ page }) => {
    const text: string[] = [];
    await page.goto("/");
    for (let i = 0; i < TOTAL; i++) {
      text.push(await page.locator(".slide-layer").last().innerText());
      await page.keyboard.press("ArrowRight");
      await page.waitForTimeout(100);
    }
    const all = text.join("\n").toLowerCase();
    expect(all).not.toMatch(/llm|gpt|нейросет|production-ready|готов к промышленн/);
    expect(all).toContain("без интеграции с банком");
    expect(all).toContain("синтетическ");
  });
});
