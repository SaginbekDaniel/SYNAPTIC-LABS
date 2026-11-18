import { expect, test, type Page } from "@playwright/test";

const STEPS = [4, 6, 8, 5, 4, 1];
const go = async (page: Page, slide: number, step = 1) => {
  await page.goto(`/#/${slide}/${step}`);
  await page.reload();
  await expect(page.locator(".slide-layer")).toHaveCount(1);
};
const announce = (page: Page) => page.getByTestId("announce");

test.describe("navigation engine", () => {
  test("keyboard: arrows, space, shift+arrows, numbers, home/end, restart", async ({ page }) => {
    await page.goto("/");
    await expect(announce(page)).toContainText("Слайд 1 из 6");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("Space");
    await expect(page).toHaveURL(/#\/1\/3$/);
    for (let i = 0; i < 2; i++) await page.keyboard.press("ArrowRight"); // 1/4 then slide 2
    await expect(page).toHaveURL(/#\/2\/1$/);
    await page.keyboard.press("ArrowLeft"); // back lands on the finished state of slide 1
    await expect(page).toHaveURL(/#\/1\/4$/);
    await page.keyboard.press("Shift+ArrowRight");
    await expect(page).toHaveURL(/#\/2\/1$/);
    await page.keyboard.press("4");
    await expect(announce(page)).toContainText("Слайд 4 из 6");
    await page.keyboard.press("End");
    await expect(page).toHaveURL(/#\/6\/1$/);
    await page.keyboard.press("ArrowRight"); // no-op at the end
    await expect(page).toHaveURL(/#\/6\/1$/);
    await page.keyboard.press("Home");
    await expect(page).toHaveURL(/#\/1\/1$/);
    await page.keyboard.press("5");
    await page.keyboard.press("r");
    await expect(page).toHaveURL(/#\/1\/1$/);
  });

  test("deep links restore exact state and the hash follows navigation", async ({ page }) => {
    await go(page, 3, 7);
    await expect(announce(page)).toContainText("Слайд 3 из 6");
    await expect(page.getByRole("button", { name: "Легитимное", exact: true })).toBeVisible();
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(/#\/3\/8$/);
  });

  test("overview dialog: quick navigation, Escape, focus restore", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Обзор слайдов/ }).focus();
    await page.keyboard.press("Enter");
    const dlg = page.getByRole("dialog", { name: "Обзор слайдов" });
    await expect(dlg).toBeVisible();
    await expect(dlg.locator(".ov-card")).toHaveCount(6);
    await page.keyboard.press("Escape");
    await expect(dlg).toBeHidden();
    await expect(page.getByRole("button", { name: /Обзор слайдов/ })).toBeFocused();
    await page.keyboard.press("o");
    await dlg.locator(".ov-card").nth(4).click();
    await expect(dlg).toBeHidden();
    await expect(announce(page)).toContainText("Слайд 5 из 6");
  });

  test("progress segments jump to slides", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Слайд 3: /, includeHidden: false }).click();
    await expect(announce(page)).toContainText("Слайд 3 из 6");
  });

  test("presenter notes show the current step, a timer and the next slide", async ({ page }) => {
    await go(page, 2, 3);
    await page.keyboard.press("n");
    const notes = page.getByRole("complementary", { name: "Заметки докладчика" });
    await expect(notes).toBeVisible();
    await expect(notes.locator("li.on")).toContainText("Детекторы ищут воронку");
    await expect(notes).toContainText("Не просто обнаруживаем");
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
    await expect(page).toHaveURL(/#\/1\/2$/);
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

test.describe("slide interactions", () => {
  test("01: the lens switch flips between per-transfer and network views", async ({ page }) => {
    await go(page, 1, 4);
    const tx = page.getByRole("button", { name: "По одному переводу" });
    const net = page.getByRole("button", { name: "По сети" });
    await expect(tx).toHaveAttribute("aria-pressed", "true");
    await net.click();
    await expect(net).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Воронка сбора")).toBeVisible();
  });

  test("02: stages are clickable and Hypothesis Testing is labelled as not merged", async ({ page }) => {
    await go(page, 2, 1);
    await page.getByRole("button", { name: "Шаг 4: Проверка гипотез" }).click();
    await expect(page).toHaveURL(/#\/2\/4$/);
    await expect(page.getByText("В PR №3 · не в main")).toBeVisible();
    await page.getByRole("button", { name: "Шаг 6: Решение аналитика" }).click();
    await expect(page.getByText("Система не блокирует счета и ничего не отправляет", { exact: false }).first()).toBeVisible();
  });

  test("03: temporal scenarios, peer toggle, hypotheses and evidence respond", async ({ page }) => {
    await go(page, 3, 5);
    await page.getByRole("button", { name: "Неоднозначна" }).click();
    await expect(page.getByText("порядок внутри дня неизвестен")).toBeVisible();
    await page.getByRole("button", { name: "Противоречит" }).click();
    await expect(page.getByText("Вывод раньше поступления")).toBeVisible();

    await page.keyboard.press("ArrowRight");
    await page.getByRole("button", { name: "Выброс" }).click();
    await expect(page.getByText("порога выброса среди счетов похожей активности")).toBeVisible();

    await page.keyboard.press("ArrowRight"); // hypotheses
    await expect(page.getByText("Перевес: подозрительное объяснение")).toBeVisible();
    await page.getByRole("button", { name: "Наблюдения B" }).click();
    await expect(page.getByText("Перевес: легитимное объяснение")).toBeVisible();
    await expect(page.getByText("Приоритет ограничен до «Низкий»")).toBeVisible();
    await page.getByRole("button", { name: "Легитимное", exact: true }).click();
    await expect(page.getByText("Контрагенты платят в разные дни").first()).toBeVisible();
    await expect(page.getByText(/\d\d\s?%/).first()).toHaveCount(0); // no confidence percentages in the panel

    await page.keyboard.press("ArrowRight"); // evidence
    const row = page.getByRole("button", { name: /5 счетов направили/ });
    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "true");
  });

  test("04: real screenshots load, hotspots zoom, repository link is real", async ({ page }) => {
    await go(page, 4, 1);
    const img = page.locator(".vimg img");
    await expect(img).toBeVisible();
    expect(await img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
    const before = await page.locator(".vimg").evaluate((el) => getComputedStyle(el).transform);
    await page.getByRole("button", { name: "2 Генерация и анализ" }).click();
    await page.waitForTimeout(1000);
    const after = await page.locator(".vimg").evaluate((el) => getComputedStyle(el).transform);
    expect(after).not.toBe(before);
    await page.getByRole("button", { name: "Весь экран" }).click();
    await expect(page.getByRole("link", { name: /Репозиторий на GitHub/ })).toHaveAttribute("href", "https://github.com/SaginbekDaniel/SYNAPTIC-LABS");
    for (let s = 2; s <= 5; s++) {
      await page.keyboard.press("ArrowRight");
      await expect(page).toHaveURL(new RegExp(`#/4/${s}$`));
      await page.waitForTimeout(500);
      expect(await img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
    }
  });

  test("05: verified figures, mandatory disclaimer and provenance chips", async ({ page }) => {
    await go(page, 5, 4);
    const slide = page.locator(".slide-layer");
    await expect(slide.getByText("Синтетический benchmark, 60 датасетов. Не оценка точности на реальных данных банка")).toBeVisible();
    await page.waitForTimeout(2200);
    for (const v of ["50,7 %", "15,9 %", "73,3 %", "74,8 %", "46,5 %", "59,3 %", "17,8 %", "9,8 %"]) await expect(slide).toContainText(v);
    await expect(slide.getByText("Артефакт в PR №3 · ещё не в main")).toBeVisible();
    await slide.getByRole("button", { name: "Что не решено" }).click();
    await expect(slide.getByText("22 из 23")).toBeVisible();
  });

  test("06: finale content", async ({ page }) => {
    await go(page, 6, 1);
    await expect(page.getByRole("heading", { name: "NEXORA AI", exact: true })).toBeVisible();
    await expect(page.locator(".s6-head")).toHaveText("От подозрения — к проверяемому расследованию");
    for (const p of ["Объяснимость", "Доказательства", "Решение аналитика"]) await expect(page.locator(".pillars")).toContainText(p);
  });
});

test.describe("layout integrity", () => {
  /** Every visible element of every reveal state must sit inside the 80px safe area (canvas coordinates). */
  for (let slide = 1; slide <= 6; slide++) {
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
          const skip = ".s6-bg, .s6-bg *, .wm-glow, .vimg, .vimg *, .halo";
          document.querySelectorAll(".slide-layer *").forEach((el) => {
            if (el.matches(skip) || el.closest(".s6-bg, .vimg, .vport") && !el.classList.contains("vport")) return;
            const cs = getComputedStyle(el);
            if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity) === 0) return;
            if (el.closest("[aria-hidden='true']") && !el.closest(".vport")) return;
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
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 1920, height: 1080 });
    const small: string[] = [];
    for (let slide = 1; slide <= 6; slide++) {
      await go(page, slide, 1);
      await page.waitForTimeout(2500);
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
      small.push(...found.map((f) => `slide ${slide}: ${f}`));
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
    await go(page, 6, 1);
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
    for (let i = 0; i < 27; i++) {
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
    for (let i = 0; i < 28; i++) {
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
