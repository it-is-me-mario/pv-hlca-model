"""Check local documentation links and notebook syntax without model execution."""
import ast
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
errors = []
for file in [ROOT / "README.md", *ROOT.glob("docs/*.md"), ROOT / "paper/README.md"]:
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", file.read_text()):
        url = urlsplit(target)
        if not url.scheme and url.path and not (file.parent / unquote(url.path)).exists():
            errors.append(f"{file.relative_to(ROOT)}: missing {target}")
notebook = json.loads((ROOT / "notebooks/Use_the_model.ipynb").read_text())
for i, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] == "code":
        try:
            ast.parse("".join(cell["source"]))
        except SyntaxError as exc:
            errors.append(f"Use_the_model.ipynb cell {i}: {exc}")
if errors:
    raise SystemExit("\n".join(errors))
print("Local documentation links and model notebook syntax: OK")
