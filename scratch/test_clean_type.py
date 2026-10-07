import re

def _clean_mermaid_type(data_type: str) -> str:
    dt = data_type.lower().strip()
    if "char" in dt or "text" in dt:
        return "string"
    if "int" in dt or "serial" in dt:
        return "int"
    if "numeric" in dt or "decimal" in dt or "real" in dt or "double" in dt or "float" in dt:
        return "float"
    if "bool" in dt:
        return "boolean"
    if "date" in dt or "time" in dt:
        return "datetime"
    if "uuid" in dt:
        return "uuid"
    if "json" in dt:
        return "json"
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', dt)
    return clean or "string"

print(_clean_mermaid_type("character varying"))
print(_clean_mermaid_type("double precision"))
print(_clean_mermaid_type("timestamp with time zone"))
