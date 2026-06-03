import json
import urllib.request
import urllib.error

url = "https://api.web3forms.com/submit"
access_key = "81c99014-3d64-453f-a083-c96698dde3e5"

payloads = [
    # Test 1: Standard simple submission
    {
        "access_key": access_key,
        "name": "PTIA Co-Piloto",
        "email": "noreply@ptia.pt",
        "subject": "PTIA Test 1",
        "message": "Teste 1 do sistema de alertas."
    },
    # Test 2: Submission with minimal fields
    {
        "access_key": access_key,
        "subject": "PTIA Test 2",
        "message": "Teste 2 do sistema de alertas."
    }
]

for i, payload in enumerate(payloads, 1):
    print(f"=== Running Test {i} ===")
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            resp_body = res.read().decode("utf-8")
            print(f"Success! Status code: {res.status} | Response:\n{resp_body}")
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8")
        print(f"HTTP Error {e.code}: {e.reason} | Response:\n{resp_body}")
    except Exception as e:
        print(f"Unexpected Error: {e}")
