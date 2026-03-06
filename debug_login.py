from playwright.sync_api import sync_playwright
import getpass

username = input("Username: ")
password = getpass.getpass("Password: ")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://myeducation.gov.bc.ca/aspen/logon.do")

    page.wait_for_selector("input[formcontrolname='username']", timeout=15000)
    page.fill("input[formcontrolname='username']", username)
    page.fill("input[formcontrolname='password']", password)
    page.click("button:has-text('Log In')")

    try:
        page.wait_for_url("**/home.do*", timeout=15000)
        print(f"\nLogin SUCCESS! URL: {page.url}")
    except Exception:
        print(f"\nLogin FAILED. URL: {page.url}")
        print(f"Page text: {page.inner_text('body')[:500]}")
        page.screenshot(path="debug-fail.png")
        browser.close()
        exit(1)

    print("\nAll cookies:")
    for c in page.context.cookies():
        print(f"  {c['name']} = {c['value'][:60]}  (domain={c['domain']}, path={c['path']})")

    browser.close()
