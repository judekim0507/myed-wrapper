# myed-wrapper

CLI wrapper for [MyEducation BC](https://myeducation.gov.bc.ca) (Aspen). View your classes, grades, and assignments from the terminal.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
python myed.py
```

You'll be prompted to either:

1. **Paste your cookie string** — grab it from Chrome DevTools (Network tab → any request → Request Headers → Cookie)
2. **Login with username/password**

From there, select a class by number to view assignments and grades.

## As a library

```python
from myed import MyEdClient

client = MyEdClient(cookies="JSESSIONID=...; ApplicationGatewayAffinity=...")
# or
client = MyEdClient()
client.login("username", "password")

client.get_classes()        # list of classes with grades
client.get_class_detail(oid) # select a class
client.get_assignments()     # assignments for selected class
client.get_student_info()    # student profile
```

## Notes

- Sessions expire after ~1 hour of inactivity
- The cookie method requires **all** cookies (JSESSIONID alone won't work due to Azure gateway affinity)
- MyEd has no JSON API — this scrapes the HTML
- i asked claude to build this entirely btw. i didnt even review the codes.
