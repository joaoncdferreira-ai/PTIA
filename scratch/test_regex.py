import re

def clean_linkedin_text(text: str) -> str:
    # Surgically strip @ mentions using standard group capture
    return re.sub(r"(^|\s|[()\[\]])@(\w+)", r"\1\2", text)

# Test cases
test_cases = [
    ("O governo dos EUA... da @NVIDIA e @AMD a compromissos", "O governo dos EUA... da NVIDIA e AMD a compromissos"),
    ("info@ptia.pt", "info@ptia.pt"),
    ("(@NVIDIA)", "(NVIDIA)"),
    ("@Daniela Braga é a CEO", "Daniela Braga é a CEO"),
    ("Email: joao@gmail.com para mais info", "Email: joao@gmail.com para mais info"),
    ("Empresas [@Defined.ai e @Unbabel] lideram.", "Empresas [Defined.ai e Unbabel] lideram.") # Wait, Defined.ai has a dot. Let's check!
]

print("=== Running Regex Tests ===")
all_ok = True
for idx, (inp, expected) in enumerate(test_cases, start=1):
    out = clean_linkedin_text(inp)
    if out == expected:
        print(f"Test {idx}: OK")
    else:
        print(f"Test {idx}: FAILED! Input: {repr(inp)} | Expected: {repr(expected)} | Got: {repr(out)}")
        all_ok = False

if all_ok:
    print("All tests passed successfully!")
