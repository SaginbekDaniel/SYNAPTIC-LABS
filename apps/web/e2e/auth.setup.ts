import { test as setup } from "@playwright/test";
import { AUTH_STATE, signIn } from "./helpers";

setup("sign in once for the journey suites", async ({ page }) => {
  await page.goto("/");
  await signIn(page);
  await page.context().storageState({ path: AUTH_STATE });
});
