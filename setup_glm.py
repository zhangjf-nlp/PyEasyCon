"""GLM API-KEY validator and config writer."""
import sys
import yaml
from openai import OpenAI

GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
YAML_KEY = ("vl_model", "glm", "api_key")


def validate_key(api_key: str) -> bool:
    try:
        client = OpenAI(api_key=api_key, base_url=GLM_BASE_URL, timeout=15)
        client.models.list()
        return True
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def write_key(yaml_path: str, api_key: str) -> None:
    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    node = cfg
    for k in YAML_KEY[:-1]:
        node = node.setdefault(k, {})
    node[YAML_KEY[-1]] = api_key
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
    print("OK")


def read_existing_key(yaml_path: str) -> str:
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        node = cfg
        for k in YAML_KEY:
            node = node.get(k, {})
        return node if isinstance(node, str) else ""
    except Exception:
        return ""


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python setup_glm.py <yaml_path> [api_key]")
        print("  If api_key is omitted, interactive mode is used.")
        sys.exit(1)

    yaml_path = sys.argv[1]

    if len(sys.argv) >= 3:
        api_key = sys.argv[2]
    else:
        existing = read_existing_key(yaml_path)
        if existing:
            print(f"Existing key found: {existing[:8]}...{existing[-4:]}")
            keep = input("Keep existing key? [Y/n]: ").strip().lower()
            if keep in ("", "y"):
                print("OK")
                sys.exit(0)
        print()
        print("EasyCon needs a free GLM API-KEY for image recognition.")
        print("Register at: https://bigmodel.cn/apikey/platform")
        print()
        api_key = input("API-KEY: ").strip()
        if not api_key:
            print("API-KEY cannot be empty.")
            sys.exit(1)

    if not validate_key(api_key):
        sys.exit(1)

    write_key(yaml_path, api_key)
