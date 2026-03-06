import requests
from bs4 import BeautifulSoup
import re


class SessionExpiredError(Exception):
    pass


class MyEdClient:
    BASE_URL = "https://myeducation.gov.bc.ca/aspen"

    def __init__(self, cookies: str | None = None):
        """
        cookies: paste your full cookie string from browser DevTools
                 (Network tab -> any request -> Request Headers -> Cookie)
                 e.g. "JSESSIONID=abc123; ApplicationGatewayAffinity=xyz789"
        """
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/145.0.0.0 Safari/537.36",
        })
        self._token = None
        if cookies:
            for pair in cookies.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    name, value = pair.split("=", 1)
                    self.session.cookies.set(name.strip(), value.strip(), domain="myeducation.gov.bc.ca")

    def _check_session(self, r):
        if "Not Logged On" in r.text and r.status_code == 404:
            raise SessionExpiredError("Session expired. Get a fresh cookie string from your browser.")

    def _get_token(self, soup):
        tag = soup.find("input", {"name": "org.apache.struts.taglib.html.TOKEN"})
        if tag:
            self._token = tag["value"]

    def login(self, username: str, password: str) -> bool:
        """Login via headless browser (the login page is an Angular SPA)."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"{self.BASE_URL}/logon.do")

            # Wait for Angular to render the form
            page.wait_for_selector("input[formcontrolname='username']", timeout=15000)

            page.fill("input[formcontrolname='username']", username)
            page.fill("input[formcontrolname='password']", password)

            # Click the "Log In" button (not type=submit, just a regular button)
            page.click("button:has-text('Log In')")

            # Wait for redirect to main app (or stay on login = failed)
            try:
                page.wait_for_url("**/home.do*", timeout=15000)
            except Exception:
                browser.close()
                return False

            # Transfer all cookies from browser to requests session
            for cookie in page.context.cookies():
                self.session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain", "myeducation.gov.bc.ca"),
                    path=cookie.get("path", "/"),
                )

            browser.close()
        return True

    def get_classes(self) -> list[dict]:
        r = self.session.get(
            f"{self.BASE_URL}/portalClassList.do",
            params={"navkey": "academics.classes.list"},
        )
        self._check_session(r)
        soup = BeautifulSoup(r.text, "html.parser")
        self._get_token(soup)
        self._list_form_data = self._extract_form(soup, "classListForm")

        classes = []
        rows = soup.find_all("tr", class_=lambda c: c and "listCell" in c)
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 6:
                continue
            text = [c.get_text(strip=True) for c in cells]
            checkbox = row.find("input", {"type": "checkbox", "name": "selectedOids"})
            oid = checkbox["value"] if checkbox else None
            classes.append({
                "oid": oid,
                "name": text[1],
                "term": text[2],
                "teacher": text[3],
                "room": text[4],
                "grade": text[5] if text[5] else None,
            })
        return classes

    def _extract_form(self, soup, form_name):
        """Extract all hidden input values from a named form."""
        form = soup.find("form", {"name": form_name})
        if not form:
            return {}
        data = {}
        for inp in form.find_all("input", {"type": "hidden"}):
            name = inp.get("name", "")
            if name:
                data[name] = inp.get("value", "")
        return data

    def get_class_detail(self, class_oid: str) -> dict:
        """Select a class and fetch its detail page (assignments, grades)."""
        # Build full form submission like the browser does
        form_data = dict(self._list_form_data)
        form_data["userEvent"] = "2100"
        form_data["userParam"] = class_oid

        r = self.session.post(
            f"{self.BASE_URL}/portalClassList.do",
            data=form_data,
        )
        soup = BeautifulSoup(r.text, "html.parser")
        self._get_token(soup)
        return {"html": r.text, "soup": soup}

    def get_assignments(self) -> list[dict]:
        """Fetch assignments from the current class detail page."""
        r = self.session.get(
            f"{self.BASE_URL}/portalAssignmentList.do",
            params={"navkey": "academics.classes.list.gcd"},
        )
        soup = BeautifulSoup(r.text, "html.parser")
        self._get_token(soup)

        assignments = []
        rows = soup.find_all("tr", class_=lambda c: c and "listCell" in c)
        for row in rows:
            cells = row.find_all("td")
            text = [c.get_text(strip=True) for c in cells]
            if len(text) >= 8:
                # cols: checkbox, name, assigned, due, weight, score(merged), pct, fraction, points, feedback
                assignments.append({
                    "name": text[1],
                    "due": text[3],
                    "pct": text[6],
                    "score": text[7],
                    "feedback": text[9] if len(text) > 9 else "",
                })
        return assignments

    def get_student_info(self) -> dict:
        r = self.session.get(
            f"{self.BASE_URL}/portalStudentDetail.do",
            params={"navkey": "myInfo.details.detail"},
        )
        self._check_session(r)
        soup = BeautifulSoup(r.text, "html.parser")
        self._get_token(soup)

        info = {}
        # Try multiple selector patterns used by Aspen
        for row in soup.find_all("tr"):
            label_td = row.find("td", class_=lambda c: c and "label" in c.lower())
            value_td = row.find("td", class_=lambda c: c and "value" in c.lower())
            if not label_td or not value_td:
                tds = row.find_all("td")
                if len(tds) == 2:
                    label_td, value_td = tds
                else:
                    continue
            key = label_td.get_text(strip=True).rstrip(":")
            val = value_td.get_text(strip=True)
            if key and val:
                info[key] = val
        return info


def clear():
    import os
    os.system("clear" if os.name != "nt" else "cls")


def box(title, lines):
    """Draw a simple box around content."""
    all_lines = [title, ""] + lines if title else lines
    width = max(len(l) for l in all_lines) + 4
    print(f"  ┌{'─' * width}┐")
    if title:
        print(f"  │  {title}{' ' * (width - len(title) - 2)}│")
        print(f"  ├{'─' * width}┤")
    for line in lines:
        print(f"  │  {line}{' ' * (width - len(line) - 2)}│")
    print(f"  └{'─' * width}┘")


def truncate(s, n):
    return s[:n - 1] + "…" if len(s) > n else s


def run_tui():
    import getpass

    clear()
    print()
    print("  ╔══════════════════════════════════╗")
    print("  ║         MyEd BC Wrapper          ║")
    print("  ╚══════════════════════════════════╝")
    print()
    print("  1) Paste cookie string from browser")
    print("  2) Login with username/password")
    print()
    choice = input("  Choose [1/2]: ").strip()

    if choice == "1":
        cookie_str = input("  Cookie: ").strip()
        client = MyEdClient(cookies=cookie_str)
    else:
        client = MyEdClient()
        user = input("  Username: ")
        pw = getpass.getpass("  Password: ")
        print("  Logging in (headless browser)...", flush=True)
        if not client.login(user, pw):
            print("\n  Login failed.")
            return

    try:
        classes = client.get_classes()
    except SessionExpiredError as e:
        print(f"\n  {e}")
        return

    while True:
        clear()
        print()
        print("  ╔══════════════════════════════════════════════════════════════╗")
        print("  ║                        MY CLASSES                           ║")
        print("  ╚══════════════════════════════════════════════════════════════╝")
        print()

        # Table header
        print(f"  {'#':>3}  {'Class':<45} {'Teacher':<25} {'Room':<10} {'Grade':<8}")
        print(f"  {'─' * 3}  {'─' * 45} {'─' * 25} {'─' * 10} {'─' * 8}")

        for i, c in enumerate(classes, 1):
            name = truncate(c["name"], 45)
            teacher = truncate(c["teacher"], 25)
            room = c["room"][:10]
            grade = c["grade"] or "—"
            print(f"  {i:>3}  {name:<45} {teacher:<25} {room:<10} {grade:<8}")

        print()
        print("  [#] View class details    [r] Refresh    [i] Student info    [q] Quit")
        print()
        cmd = input("  > ").strip().lower()

        if cmd == "q":
            print()
            break
        elif cmd == "r":
            try:
                classes = client.get_classes()
            except SessionExpiredError as e:
                print(f"\n  {e}")
                input("  Press Enter to continue...")
        elif cmd == "i":
            clear()
            print()
            try:
                info = client.get_student_info()
                lines = [f"{k}: {v}" for k, v in info.items()]
                if lines:
                    box("Student Info", lines)
                else:
                    print("  No student info found.")
            except SessionExpiredError as e:
                print(f"\n  {e}")
            print()
            input("  Press Enter to go back...")
        elif cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(classes):
                selected = classes[idx]
                view_class(client, selected)
                # Re-fetch classes to reset form state
                try:
                    classes = client.get_classes()
                except SessionExpiredError:
                    pass
            else:
                print(f"  Invalid number. Choose 1-{len(classes)}.")
                input("  Press Enter to continue...")


def view_class(client, cls):
    """View details and assignments for a selected class."""
    try:
        client.get_class_detail(cls["oid"])
        assignments = client.get_assignments()
    except SessionExpiredError as e:
        print(f"\n  {e}")
        input("  Press Enter to go back...")
        return

    while True:
        clear()
        print()
        grade_str = f"  |  Grade: {cls['grade']}" if cls["grade"] else ""
        box(cls["name"], [
            f"Teacher: {cls['teacher']}",
            f"Room: {cls['room']}  |  Term: {cls['term']}{grade_str}",
        ])
        print()

        if assignments:
            print(f"  {'#':>3}  {'Assignment':<40} {'Due':<12} {'%':<6} {'Score':<14} {'Feedback'}")
            print(f"  {'─' * 3}  {'─' * 40} {'─' * 12} {'─' * 6} {'─' * 14} {'─' * 20}")
            for i, a in enumerate(assignments, 1):
                name = truncate(a["name"], 40)
                due = a["due"][:12]
                pct = a["pct"] or "—"
                score = a["score"] or "—"
                fb = truncate(a["feedback"], 30) if a["feedback"] else ""
                print(f"  {i:>3}  {name:<40} {due:<12} {pct:<6} {score:<14} {fb}")
        else:
            print("  No assignments found.")

        print()
        print("  [b] Back    [r] Refresh")
        print()
        cmd = input("  > ").strip().lower()

        if cmd == "b":
            break
        elif cmd == "r":
            try:
                assignments = client.get_assignments()
            except SessionExpiredError as e:
                print(f"\n  {e}")
                input("  Press Enter to continue...")


if __name__ == "__main__":
    run_tui()
