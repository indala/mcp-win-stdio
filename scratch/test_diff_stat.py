import subprocess
import re

res = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True, cwd=".")
lines = res.stdout.strip().splitlines()

files = []
summary = {}
for line in lines:
    m = re.match(r"^\s*(.*?)\s+\|\s+(\d+)\s+([+-]*)", line)
    if m:
        path, count, signs = m.groups()
        files.append({
            "file": path.strip(),
            "changes": int(count),
            "insertions": signs.count("+"),
            "deletions": signs.count("-")
        })
    elif "changed" in line:
        summary["summary_line"] = line.strip()

print("Parsed files changed:", len(files))
print("Summary:", summary)
